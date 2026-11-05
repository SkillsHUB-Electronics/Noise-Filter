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
