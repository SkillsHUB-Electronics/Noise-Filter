import json, os
from importlib import resources
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")


def test_i18n_keys_match():
    load = lambda l: set(json.loads(resources.files("noise_filter.i18n").joinpath(f"{l}.json").read_text("utf-8")))
    assert load("en") == load("id")


def test_window_demo_and_live_params(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from PySide6 import QtWidgets as W
    app = W.QApplication.instance() or W.QApplication([])
    from noise_filter.ui.main_window import MainWindow
    w = MainWindow(demo=True)
    for _ in range(50):
        w._demo_frame()
    w._tick()
    sp_id = id(w.pipe.spectral)
    w.strength.setValue(150); w.hp.setValue(120); w.bypass.setChecked(True)
    assert w.pipe.cfg.strength == 1.5 and w.pipe.cfg.highpass_hz == 120 and w.pipe.cfg.bypass
    assert id(w.pipe.spectral) == sp_id          # live update must not rebuild the chain
    w.lang_cb.setCurrentIndex(1)
    assert w.start_btn.text() == "Mulai"
    w.close()
    assert (tmp_path / "NoiseFilter" / "config.json").exists()


def test_ai_mode_uses_installed_model(tmp_path, monkeypatch):
    pytest.importorskip("onnxruntime")
    torch = pytest.importorskip("torch")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("NF_CORE_DISABLE", "1")         # Python engine: ONNX via onnxruntime
    from training.model import NFNet
    from training.export import export_onnx
    model = tmp_path / "nfnet-test.onnx"
    export_onnx(NFNet(hidden=32), model)
    from noise_filter import model_update
    from noise_filter.core import native
    monkeypatch.setattr(native, "_lib", None)
    monkeypatch.setattr(model_update, "current_model",
                        lambda: {"name": "nfnet", "version": "test", "path": model})
    monkeypatch.setattr(model_update, "current_model_path", lambda: str(model))
    from PySide6 import QtWidgets as W
    app = W.QApplication.instance() or W.QApplication([])
    from noise_filter.ui.main_window import MainWindow
    w = MainWindow(demo=True)
    assert "test" in w.mode_cb.itemText(2)
    w.mode_cb.setCurrentIndex(2)
    assert w.pipe.cfg.denoise == "onnx" and w.pipe.cfg.onnx_model == str(model)
    for _ in range(5):
        w._demo_frame()
    w._model_update_done({"name": "nfnet", "version": "test2", "path": model}, None)
    assert "test2" in w.status.text()
    w.close()


def test_model_update_button_reports_result(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from PySide6 import QtWidgets as W
    app = W.QApplication.instance() or W.QApplication([])
    from noise_filter import model_update
    from noise_filter.ui.main_window import MainWindow
    w = MainWindow(demo=True)
    assert w.train_btn.isEnabled()
    monkeypatch.setattr(model_update, "update_in_background", lambda cb: cb(None, None))
    monkeypatch.setattr(model_update, "current_model", lambda: {"version": "2026.11.12"})
    w.train_btn.click()
    assert "2026.11.12" in w.status.text() and w.train_btn.isEnabled()
    monkeypatch.setattr(model_update, "update_in_background", lambda cb: cb(None, OSError("offline")))
    w.train_btn.click()
    assert "offline" in w.status.text()
    w.close()


def test_contribution_offer_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from PySide6 import QtWidgets as W
    app = W.QApplication.instance() or W.QApplication([])
    import numpy as np
    from noise_filter import contribute
    from noise_filter.ui import main_window as mw
    monkeypatch.setattr(contribute, "enabled", lambda: True)
    w = mw.MainWindow(demo=True)
    assert not w.contrib_cb.isHidden() and w.contrib_cb.isChecked()
    sent = []
    monkeypatch.setattr(w._uploader, "run", lambda fn, *a: sent.append((fn, a)))

    def fake_exec(dlg):
        assert not dlg.send_btn.isEnabled()          # consent is required first
        dlg.consent.setChecked(True); dlg.cat.setCurrentIndex(1); dlg._send()
        return W.QDialog.Accepted
    monkeypatch.setattr(mw.ContributeDialog, "exec", fake_exec)
    w._offer_sample(None)                             # screening failed: nothing offered, nothing sent
    assert not sent
    x = np.zeros(48000 * 3, np.float32)
    w._offer_sample(x)
    assert sent and sent[0][0] is contribute.upload and sent[0][1][1] == "traffic"
    assert contribute.load_state()["consent"] == "cc0-v1"

    def never_exec(dlg):
        dlg._never(); return W.QDialog.Rejected
    monkeypatch.setattr(mw.ContributeDialog, "exec", never_exec)
    w._offer_sample(x)
    assert not w.contrib_cb.isChecked() and contribute.load_state()["ask"] is False
    w.close()
