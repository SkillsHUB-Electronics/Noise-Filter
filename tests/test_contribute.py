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
        assert set(m) == {"install_id", "category", "app_version", "os", "consent"}   # nothing else leaves the PC
        assert contribute.load_state()["sent"] == 1
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
