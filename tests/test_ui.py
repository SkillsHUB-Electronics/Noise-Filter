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


def test_layout_fits_small_screens(tmp_path, monkeypatch):
    """Long device names and translations must not push widgets on top of each other."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from PySide6 import QtWidgets as W
    app = W.QApplication.instance() or W.QApplication([])
    from noise_filter.ui.main_window import MainWindow
    w = MainWindow(demo=True)
    for i in range(2):
        w.in_cb.addItem("Microphone Array (Realtek(R) Audio) with a very long driver name " * 2, 100 + i)
    w.mode_cb.setItemText(2, "AI model  (nfnet 2026.11.12-very-long-build-name)")
    w.status.setText("x" * 400)
    for i in range(2):
        w.lang_cb.setCurrentIndex(i)
        assert w.minimumSizeHint().width() <= 1000, w.minimumSizeHint()
    w.close()


def test_close_to_tray_and_quit(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from PySide6 import QtWidgets as W
    app = W.QApplication.instance() or W.QApplication([])
    monkeypatch.setattr(W.QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))
    quits = []
    monkeypatch.setattr(W.QApplication, "quit", staticmethod(lambda: quits.append(1)))
    from noise_filter.ui.main_window import MainWindow
    w = MainWindow(demo=True)
    w.show()
    assert w.tray.isVisible() and w.tray_cb.isChecked() and w.tray_cb.isEnabled()
    w.close()                                      # hides to the tray, keeps running
    assert not w.isVisible() and not quits and not w._shut_down
    w._update_tray()
    assert w.act_show.text() == "Show window"
    w.act_show.trigger()
    assert w.isVisible()
    w.tray_cb.setChecked(False)                    # setting off: closing really quits
    w.close()
    assert quits and w._shut_down and not w.tray.isVisible()
    import json
    data = json.loads((tmp_path / "NoiseFilter" / "config.json").read_text("utf-8"))
    assert data["close_to_tray"] is False and data["geometry"]


def test_tray_quit_menu_exits_even_with_tray_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from PySide6 import QtWidgets as W
    app = W.QApplication.instance() or W.QApplication([])
    monkeypatch.setattr(W.QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))
    quits = []
    monkeypatch.setattr(W.QApplication, "quit", staticmethod(lambda: quits.append(1)))
    from noise_filter.ui.main_window import MainWindow
    w = MainWindow(demo=True)
    w.show()
    w.act_quit.trigger()
    assert quits and w._shut_down


class _FakeEngine:
    instances = []

    def __init__(self, pipe, i, o, exclusive=False):
        self.exclusive = exclusive; self.xruns = 0; self.stopped = False
        _FakeEngine.instances.append(self)

    def start(self): pass

    def stop(self): self.stopped = True


def test_settings_and_running_state_are_remembered(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from PySide6 import QtWidgets as W, QtCore
    app = W.QApplication.instance() or W.QApplication([])
    monkeypatch.setattr(W.QApplication, "quit", staticmethod(lambda: None))
    from noise_filter.audio import engine as eng_mod
    monkeypatch.setattr(eng_mod, "Engine", _FakeEngine, raising=False)
    from noise_filter.ui.main_window import MainWindow
    w = MainWindow(demo=False)
    w.native_engine = False
    w.excl.setChecked(True); w.resume_cb.setChecked(True); w.tray_cb.setChecked(False)
    w.gain.setValue(6); w.lang_cb.setCurrentIndex(1)
    w.show(); w.resize(950, 650); app.processEvents()
    w.start_btn.setChecked(True)
    assert w.engine is _FakeEngine.instances[-1] and w.engine.exclusive
    w._update_tray(); assert w.act_run.isChecked() and "aktif" in w.tray.toolTip()
    w.close()                                       # quits while running
    assert _FakeEngine.instances[-1].stopped

    w2 = MainWindow(demo=False)
    w2.native_engine = False
    assert w2.excl.isChecked() and w2.resume_cb.isChecked() and not w2.tray_cb.isChecked()
    assert w2.pipe.cfg.output_gain_db == 6 and w2.lang == "id"
    assert (w2.width(), w2.height()) != (1100, 720)   # saved size restored (clamped to the screen)
    n = len(_FakeEngine.instances)
    QtCore.QTimer.singleShot(0, lambda: None)
    for _ in range(40):                              # auto-resume fires after 300 ms
        app.processEvents(); QtCore.QThread.msleep(10)
    assert len(_FakeEngine.instances) == n + 1 and w2.start_btn.isChecked()
    w2.start_btn.setChecked(False)                   # stopped by the user: stays off next time
    w2.close()
    w3 = MainWindow(demo=False)
    for _ in range(40):
        app.processEvents(); QtCore.QThread.msleep(10)
    assert not w3.start_btn.isChecked()
    w3.close()


def test_autostart_registry_value(monkeypatch):
    import sys, types
    from noise_filter.ui import autostart
    store = {}

    class Key:
        def __enter__(self): return self
        def __exit__(self, *a): pass
    fake = types.SimpleNamespace(
        HKEY_CURRENT_USER=1, KEY_SET_VALUE=2, REG_SZ=1,
        OpenKey=lambda *a: Key(), CreateKeyEx=lambda *a: Key(),
        QueryValueEx=lambda k, n: (store[n], 1) if n in store else (_ for _ in ()).throw(FileNotFoundError()),
        SetValueEx=lambda k, n, r, t, v: store.__setitem__(n, v),
        DeleteValue=lambda k, n: store.pop(n) if n in store else (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(autostart, "supported", lambda: True)
    monkeypatch.setattr(autostart, "_winreg", lambda: fake)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\Noise Filter\NoiseFilter.exe")
    assert not autostart.is_enabled()
    autostart.set_enabled(True)
    assert autostart.is_enabled()
    assert store["NoiseFilter"] == r'"C:\Program Files\Noise Filter\NoiseFilter.exe" ui --minimized'
    autostart.set_enabled(False); autostart.set_enabled(False)
    assert not autostart.is_enabled()
