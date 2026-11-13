"""F3: CI screening of contributed samples (R2 is replaced by an in-memory fake)."""
import io
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from noise_filter import contribute
from training import contrib_samples as cs

A = "3f2b8c1e-9a4d-4e6f-8b2a-1c3d5e7f9a0b"
B = "11111111-1111-4111-8111-111111111111"


class FakeS3:
    def __init__(self):
        self.o = {}   # key -> (bytes, meta, last_modified)

    def put(self, key, data, meta=None, age_days=0):
        self.o[key] = (data, dict(meta or {}), datetime.now(timezone.utc) - timedelta(days=age_days))

    def get_paginator(self, _):
        s = self

        class P:
            def paginate(self, Bucket, Prefix):
                yield {"Contents": [{"Key": k, "LastModified": v[2]} for k, v in sorted(s.o.items())
                                    if k.startswith(Prefix)]}
        return P()

    def head_object(self, Bucket, Key):
        return {"Metadata": self.o[Key][1]}

    def get_object(self, Bucket, Key):
        d, m, _ = self.o[Key]
        return {"Body": io.BytesIO(d), "Metadata": m}

    def copy_object(self, Bucket, Key, CopySource, Metadata, **kw):
        d, _, t = self.o[CopySource["Key"]]
        self.o[Key] = (d, Metadata, t)

    def delete_object(self, Bucket, Key):
        del self.o[Key]

    def delete_objects(self, Bucket, Delete):
        for x in Delete["Objects"]:
            del self.o[x["Key"]]

    def download_file(self, Bucket, Key, Filename):
        open(Filename, "wb").write(self.o[Key][0])


def fan(seed):
    r = np.random.default_rng(seed)
    t = np.arange(48000 * 3) / 48000
    return (0.02 * r.standard_normal(len(t)) + 0.01 * np.sin(2 * np.pi * 120 * t)).astype(np.float32)


def voice():
    t = np.arange(48000 * 3) / 48000
    ph = 2 * np.pi * np.cumsum(140 * (1 + 0.15 * np.sin(2 * np.pi * 1.3 * t))) / 48000
    return (0.1 * sum(np.sin(h * ph) / h for h in range(1, 20)) * (np.sin(2 * np.pi * 3 * t) > 0)).astype(np.float32)


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    monkeypatch.setattr(contribute, "model_keeps_voice", lambda x, p=None: None)


def test_screening_moves_samples(monkeypatch):
    s3 = FakeS3()
    good = contribute.encode_wav(fan(1))
    s3.put(f"incoming/{A}/2026-11-13-a.wav", good, {"category": "fan_ac"})
    s3.put(f"incoming/{A}/2026-11-13-b.wav", good)                                   # duplicate
    s3.put(f"incoming/{B}/2026-11-13-c.wav", contribute.encode_wav(fan(2) + voice()))  # voice
    s3.put(f"incoming/{B}/2026-11-13-d.wav", b"RIFF junk")
    stats = cs.process_incoming(s3, None)
    assert stats["to_review"] == 1 and stats["rejected:duplicate"] == 1 and stats["rejected:speech"] == 1
    assert not [k for k in s3.o if k.startswith("incoming/")]
    assert not [k for k in s3.o if k.startswith("accepted/")]     # only the developer accepts
    acc = [k for k in s3.o if k.startswith("review/")]
    assert acc == [f"review/{A}/2026-11-13-a.wav"]
    assert s3.o[acc[0]][1]["category"] == "fan_ac" and len(s3.o[acc[0]][1]["sha256"]) == 64
    rej = {k: v[1]["reason"] for k, v in s3.o.items() if k.startswith("rejected/")}
    assert rej[f"rejected/{A}/2026-11-13-b.wav"] == "duplicate"
    assert rej[f"rejected/{B}/2026-11-13-c.wav"] == "speech"
    assert rej[f"rejected/{B}/2026-11-13-d.wav"].startswith("bad wav")


def test_daily_cap(monkeypatch):
    monkeypatch.setattr(cs, "DAILY_CAP", 2)
    s3 = FakeS3()
    for i in range(4):
        s3.put(f"incoming/{A}/2026-11-13-{i}.wav", contribute.encode_wav(fan(10 + i)))
    stats = cs.process_incoming(s3, None)
    assert stats == {"to_review": 2, "rejected:daily cap": 2}


def test_duplicates_of_samples_waiting_for_review_are_rejected():
    s3 = FakeS3()
    good = contribute.encode_wav(fan(5))
    s3.put(f"incoming/{A}/2026-11-13-a.wav", good)
    cs.process_incoming(s3, None)
    s3.put(f"incoming/{B}/2026-11-14-b.wav", good)
    assert cs.process_incoming(s3, None) == {"rejected:duplicate": 1}


def test_unreviewed_accepted_samples_go_back_to_review():
    s3 = FakeS3()
    s3.put(f"accepted/{A}/old.wav", b"x", {"reason": "ok"})
    s3.put(f"accepted/{A}/ok.wav", b"x", {"reason": "ok", "reviewed": "accepted 2026-11-14T00:00:00Z"})
    assert cs.requeue_unreviewed(s3) == 1
    assert sorted(s3.o) == [f"accepted/{A}/ok.wav", f"review/{A}/old.wav"]


def test_screen_only_fetches_nothing(monkeypatch, tmp_path):
    s3 = FakeS3()
    s3.put(f"incoming/{A}/2026-11-13-a.wav", contribute.encode_wav(fan(7)))
    s3.put(f"accepted/{B}/x.wav", b"x", {"reviewed": "accepted 2026-11-14T00:00:00Z"})
    monkeypatch.setattr(cs, "client", lambda: s3)
    monkeypatch.chdir(tmp_path)
    r = cs.main(["--screen-only", "--model", "none.onnx"])
    assert r["screening"] == {"to_review": 1} and r["waiting_for_review"] == 1 and r["accepted_total"] == 1
    assert not (tmp_path / "data").exists()


def test_purge_and_selection():
    s3 = FakeS3()
    s3.put(f"rejected/{A}/old.wav", b"x", age_days=40)
    s3.put(f"rejected/{A}/new.wav", b"x", age_days=1)
    assert cs.purge_rejected(s3) == 1 and f"rejected/{A}/new.wav" in s3.o
    keys = [f"accepted/{A}/{i}.wav" for i in range(100)] + [f"accepted/{B}/{i}.wav" for i in range(3)]
    sel = cs.select_for_training(keys, limit=1000)
    assert sum(k.split("/")[1] == A for k in sel) == 5 and sum(k.split("/")[1] == B for k in sel) == 3
    assert len(cs.select_for_training(keys, limit=4)) == 4
