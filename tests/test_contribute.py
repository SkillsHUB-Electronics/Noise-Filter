"""F3: noise sample contributions - screening, encoding and the upload protocol."""
import io
import json
import threading
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest

from noise_filter import contribute

SR = 48_000
t = np.arange(SR * 3) / SR
rng = np.random.default_rng(0)


def fan():
    return (0.02 * rng.standard_normal(len(t)) + 0.01 * np.sin(2 * np.pi * 120 * t)).astype(np.float32)


def voice():
    """Harmonic voice with moving pitch and syllables, like the training data's synthetic speech."""
    f0 = 140 * (1 + 0.15 * np.sin(2 * np.pi * 1.3 * t))
    ph = 2 * np.pi * np.cumsum(f0) / SR
    x = sum(np.sin(h * ph) / h for h in range(1, 20))
    env = (np.sin(2 * np.pi * 3 * t) > 0).astype(float)
    return (0.1 * x * env).astype(np.float32)


def test_screening_accepts_noise_and_rejects_voice(monkeypatch):
    monkeypatch.setattr(contribute, "model_keeps_voice", lambda x, p=None: None)  # heuristic only
    assert contribute.check_sample(fan()) == (True, "ok")
    assert contribute.check_sample(fan() + voice())[1] == "speech"
    assert contribute.check_sample(fan()[:SR])[1] == "too short"
    assert contribute.check_sample(np.zeros(len(t), np.float32))[1] == "silent"
    assert contribute.check_sample(np.ones(len(t), np.float32))[1] == "clipped"


def test_model_opinion_also_blocks(monkeypatch):
    monkeypatch.setattr(contribute, "model_keeps_voice", lambda x, p=None: True)
    assert contribute.check_sample(fan())[1] == "speech"


def test_prepare_trims_and_drops_gappy_recordings(monkeypatch):
    monkeypatch.setattr(contribute, "model_keeps_voice", lambda x, p=None: False)
    x = fan()
    y = contribute.prepare(x)
    assert len(y) == len(x) - int(contribute.TRIM_START * SR)
    assert contribute.prepare(x, dropped=2) is None


def test_encode_wav():
    b = contribute.encode_wav(fan())
    with wave.open(io.BytesIO(b)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, SR, len(t))


def test_install_id_is_stable_and_random(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    a = contribute.install_id()
    assert a == contribute.install_id() and len(a) == 36
    monkeypatch.setenv("APPDATA", str(tmp_path / "other"))
    assert contribute.install_id() != a


def test_upload_and_delete_protocol(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    seen = {}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def do_POST(self):
            seen["path"], seen["meta"] = self.path, json.loads(self.headers["X-NF-Meta"])
            seen["body"] = self.rfile.read(int(self.headers["Content-Length"]))
            self._reply(201, {"ok": True, "id": "2026-11-13-abc"})

        def do_DELETE(self):
            seen["delete"] = self.path
            self._reply(200, {"ok": True, "deleted": 3})

        def _reply(self, code, obj):
            b = json.dumps(obj).encode()
            self.send_response(code); self.send_header("Content-Length", str(len(b))); self.end_headers()
            self.wfile.write(b)

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    # enabled() requires https in the app; the test talks plain http to a local server
    monkeypatch.setattr(contribute, "SAMPLES_URL", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setattr(contribute, "enabled", lambda: True)
    try:
        assert contribute.upload(fan(), "fan_ac") == "2026-11-13-abc"
        assert seen["path"] == "/v1/samples" and seen["body"][:4] == b"RIFF"
        m = seen["meta"]
        assert m["category"] == "fan_ac" and m["consent"] == "cc0-v1" and m["install_id"] == contribute.install_id()
        assert set(m) == {"install_id", "category", "app_version", "os", "consent", "source"}  # nothing else leaves the PC
        assert m["source"] == "mic"
        assert contribute.load_state()["sent"] == 1
        assert contribute.upload_clips([fan(), fan()], "traffic") == 2
        assert seen["meta"]["source"] == "file" and contribute.load_state()["sent"] == 3
        with pytest.raises(ValueError):
            contribute.upload(fan(), "speech")
        assert contribute.delete_my_samples() == 3
        assert seen["delete"] == f"/v1/samples?install_id={contribute.install_id()}"
    finally:
        srv.shutdown()


def test_disabled_without_service(monkeypatch):
    monkeypatch.setattr(contribute, "SAMPLES_URL", "")
    assert not contribute.enabled()
    with pytest.raises(RuntimeError):
        contribute.upload(fan(), "fan_ac")


def _wav_bytes(x, rate, ch=1, bits=16, tag=1, extensible=False):
    """Hand-built WAV in several encodings (the stdlib wave module writes only PCM)."""
    x = np.repeat(np.asarray(x, np.float64)[:, None], ch, 1).reshape(-1)
    if tag == 3:
        pcm = x.astype("<f4" if bits == 32 else "<f8").tobytes()
    elif bits == 8:
        pcm = (x * 127 + 128).astype(np.uint8).tobytes()
    elif bits == 24:
        v = (x * (2 ** 23 - 1)).astype(np.int32)
        pcm = np.stack([v & 255, (v >> 8) & 255, (v >> 16) & 255], 1).astype(np.uint8).tobytes()
    else:
        pcm = (x * (2 ** (bits - 1) - 1)).astype(f"<i{bits // 8}").tobytes()
    ba = ch * bits // 8
    fmt_tag = 0xFFFE if extensible else tag
    fmt = (fmt_tag.to_bytes(2, "little") + ch.to_bytes(2, "little") + rate.to_bytes(4, "little")
           + (rate * ba).to_bytes(4, "little") + ba.to_bytes(2, "little") + bits.to_bytes(2, "little"))
    if extensible:
        fmt += (22).to_bytes(2, "little") + bits.to_bytes(2, "little") + b"\0\0\0\0" + tag.to_bytes(2, "little") + b"\0" * 14
    body = b"WAVE" + b"fmt " + len(fmt).to_bytes(4, "little") + fmt + b"LIST" + (4).to_bytes(4, "little") + b"INFO"
    body += b"data" + len(pcm).to_bytes(4, "little") + pcm
    return b"RIFF" + len(body).to_bytes(4, "little") + body


@pytest.mark.parametrize("bits,tag,ch,ext", [(8, 1, 1, False), (16, 1, 2, False), (24, 1, 1, False),
                                             (32, 1, 1, False), (32, 3, 2, False), (64, 3, 1, False),
                                             (24, 1, 2, True)])
def test_parse_wav_formats(bits, tag, ch, ext):
    x = 0.5 * np.sin(2 * np.pi * 440 * np.arange(4410) / 44100)
    y, rate = contribute.parse_wav(_wav_bytes(x, 44100, ch, bits, tag, ext))
    assert rate == 44100 and len(y) == len(x)
    assert np.max(np.abs(y - x)) < (0.02 if bits == 8 else 1e-3)


def test_parse_wav_rejects_other_files():
    for b in (b"", b"ID3\x04" + b"\0" * 100, b"RIFF\0\0\0\0AVI LIST"):
        with pytest.raises(contribute.AudioFileError):
            contribute.parse_wav(b)


def test_resample_keeps_tone_and_length():
    r = 44100
    x = np.sin(2 * np.pi * 1000 * np.arange(r) / r).astype(np.float32)
    y = contribute.resample(x, r)
    assert len(y) == SR
    f = np.argmax(np.abs(np.fft.rfft(y))) * SR / len(y)
    assert abs(f - 1000) < 2 and abs(np.sqrt(np.mean(y ** 2)) - np.sqrt(0.5)) < 0.01


def test_load_audio_file(tmp_path):
    p = tmp_path / "fan.wav"
    long_fan = np.tile(fan(), 3)                                # 9 s
    p.write_bytes(_wav_bytes(long_fan, 44100, 2))
    y = contribute.load_audio_file(p)
    assert abs(len(y) - len(long_fan) * SR / 44100) <= 1
    (tmp_path / "x.mp3").write_bytes(b"ID3")
    with pytest.raises(contribute.AudioFileError, match="unsupported"):
        contribute.load_audio_file(tmp_path / "x.mp3")
    got = contribute.load_audio_file(tmp_path / "x.mp3", decoder=lambda path: (fan(), SR))
    assert len(got) == len(t)
    with pytest.raises(contribute.AudioFileError, match="too_short"):
        contribute.load_audio_file(tmp_path / "x.mp3", decoder=lambda path: (fan()[:SR], SR))
    with pytest.raises(contribute.AudioFileError, match="too_long"):
        contribute.load_audio_file(tmp_path / "x.mp3", decoder=lambda path: (np.zeros(601 * 8000, np.float32), 8000))


def test_file_clips_spread_and_screen(monkeypatch):
    monkeypatch.setattr(contribute, "model_keeps_voice", lambda x, p=None: None)
    noise = np.tile(fan(), 40)                                  # 120 s
    clips, dropped = contribute.file_clips(noise)
    assert len(clips) == contribute.MAX_FILE_CLIPS and not dropped
    assert all(len(c) == 10 * SR for c in clips)
    short, _ = contribute.file_clips(fan())                     # 3 s: one clip, the whole file
    assert len(short) == 1 and len(short[0]) == len(t)
    talk = np.tile(fan() + voice(), 10)                         # voice everywhere: nothing is kept
    clips, dropped = contribute.file_clips(talk)
    assert clips == [] and dropped == {"speech": 3}
