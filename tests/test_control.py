"""Command-line / MCP control of the running app (noise_filter.remote, ui.control_server, mcp_server)."""
import io
import json
import os
import threading
import time
import uuid

import pytest

from noise_filter import mcp_server, remote


def test_parse_and_coerce():
    assert remote.parse_value("1.5") == 1.5 and remote.parse_value("0") == 0 and remote.parse_value("true") is True
    assert remote.parse_value("off") == "off"
    assert remote.coerce("gate_enabled", "off") is False and remote.coerce("bypass", 1) is True
    assert remote.coerce("highpass_hz", 0) == 0.0
    assert remote.coerce("denoise", "AI") == "onnx" and remote.coerce("denoise", "off") == "off"
    for name, value in (("strength", 3), ("strength", "x"), ("denoise", "loud"), ("nope", 1), ("bypass", "maybe")):
        with pytest.raises(remote.ControlError):
            remote.coerce(name, value)


def test_not_running(monkeypatch):
    monkeypatch.setenv("NF_CONTROL_NAME", f"nf-test-{uuid.uuid4().hex[:8]}")
    with pytest.raises(remote.NotRunning):
        remote.request("status", timeout=2)
    assert not remote.is_running()


def _rpc(*msgs):
    out = io.BytesIO()
    mcp_server.serve(io.BytesIO(b"".join(json.dumps(m).encode() + b"\n" for m in msgs)), out)
    return [json.loads(l) for l in out.getvalue().splitlines()]


def test_mcp_protocol(monkeypatch):
    monkeypatch.setenv("NF_CONTROL_NAME", f"nf-test-{uuid.uuid4().hex[:8]}")
    r = _rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
             {"jsonrpc": "2.0", "method": "notifications/initialized"},
             {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
             {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_status", "arguments": {}}},
             {"jsonrpc": "2.0", "id": 4, "method": "nope"})
    assert [m["id"] for m in r] == [1, 2, 3, 4]               # the notification gets no answer
    assert r[0]["result"]["protocolVersion"] == "2025-06-18" and "tools" in r[0]["result"]["capabilities"]
    names = {t["name"] for t in r[1]["result"]["tools"]}
    assert {"get_status", "start_filter", "stop_filter", "set_settings", "set_eq_presets", "learn_noise"} <= names
    props = next(t for t in r[1]["result"]["tools"] if t["name"] == "set_settings")["inputSchema"]["properties"]
    assert props["strength"]["maximum"] == 2.0 and props["denoise"]["enum"] == ["off", "spectral", "ai"]
    assert r[2]["result"]["isError"] and "not running" in r[2]["result"]["content"][0]["text"]
    assert r[3]["error"]["code"] == -32601


def test_control_running_window(tmp_path, monkeypatch):
    """A real window with its control server, driven from another thread like nfctl would."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    pytest.importorskip("pyqtgraph")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    name = f"nf-test-{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("NF_CONTROL_NAME", name)
    from PySide6 import QtWidgets as W
    app = W.QApplication.instance() or W.QApplication([])
    from noise_filter.ui.main_window import MainWindow
    from noise_filter.ui.control_server import listen
    w = MainWindow(demo=True)
    server = listen(name, w)

    def call(cmd, **args):
        box = {}
        def work():
            try:
                box["r"] = remote.request(cmd, timeout=10, **args)
            except Exception as e:
                box["e"] = e
        t = threading.Thread(target=work); t.start()
        end = time.monotonic() + 10
        while t.is_alive() and time.monotonic() < end:
            app.processEvents(); time.sleep(0.005)
        t.join(1)
        if "e" in box:
            raise box["e"]
        return box["r"]

    try:
        assert call("ping")["app"] == "Noise Filter"
        st = call("status")
        assert st["running"] is False and st["demo"] is True and "strength" in st["settings"]
        s = call("set", strength=1.3, highpass_hz=0, gate_enabled="off", comp_ratio=4.5, limiter_ceiling_db=-2.5)
        assert s["strength"] == 1.3 and s["highpass_hz"] == 0 and s["gate_enabled"] is False
        c = w.pipe.cfg
        assert (c.strength, c.highpass_hz, c.gate_enabled, c.comp_ratio, c.limiter_ceiling_db) == (1.3, 0, False, 4.5, -2.5)
        assert w.strength.value() == 130 and not w.gate_on.isChecked()        # the window shows the same
        with pytest.raises(remote.ControlError, match="between"):
            call("set", strength=5, highpass_hz=10)
        assert w.pipe.cfg.highpass_hz == 0                                    # nothing applied on error
        p = call("set_eq_presets", presets=["voice_clarity", "Remove 50 Hz hum"])
        assert sum(x["selected"] for x in p["presets"]) == 2 and w.pipe.cfg.eq_enabled
        assert call("set_eq_presets", presets=[])["enabled"] is False
        with pytest.raises(remote.ControlError, match="unknown preset"):
            call("set_eq_presets", presets=["nope"])
        assert call("learn_noise")["seconds"] > 0
        assert call("status")["learning_noise"] is True
        with pytest.raises(remote.ControlError, match="demo"):
            call("start")
        assert call("hide")["window_visible"] is False and not w.isVisible()
        with pytest.raises(remote.ControlError, match="unknown command"):
            call("format_disk")
        from noise_filter.ui import settings
        assert settings.load()["pipeline"]["strength"] == 1.3                 # remembered like a UI change
    finally:
        server.close()
        w._quitting = True
        w.close()
