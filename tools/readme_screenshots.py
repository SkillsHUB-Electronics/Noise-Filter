"""Render the screenshots in docs/images/ from the real app window.

Runs the Qt UI offscreen in demo mode (a synthetic voice + noise signal, no audio
device needed), switches tabs and themes, and saves each view as a PNG.

    pip install -e .[ui,dev]
    python tools/readme_screenshots.py            # writes docs/images/*.png

Works on Windows, macOS and Linux. The device names shown are placeholders.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["NF_NO_UPDATE_CHECK"] = "1"
# keep the user's real settings untouched
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="nf-shots-")

OUT = Path(__file__).resolve().parents[1] / "docs" / "images"
SIZE = (1280, 820)
INPUT = "Microphone (USB Audio Device)"
OUTPUT = "CABLE Input (VB-Audio Virtual Cable)"


def main() -> int:
    from PySide6 import QtCore, QtWidgets as W
    import pyqtgraph as pg

    pg.setConfigOptions(antialias=True)
    app = W.QApplication.instance() or W.QApplication(sys.argv)
    app.setApplicationName("Noise Filter")
    from noise_filter.ui import theme
    from noise_filter.ui.app import app_icon
    from PySide6 import QtGui
    app.setWindowIcon(app_icon(QtGui))
    from noise_filter.ui.main_window import MainWindow
    from noise_filter.i18n import tr

    def fake_devices(self):
        self.in_cb.clear(); self.out_cb.clear()
        self.in_cb.addItem(INPUT, 0); self.out_cb.addItem(OUTPUT, 1)

    MainWindow.refresh_devices = fake_devices
    w = MainWindow(demo=True)
    w.resize(*SIZE)
    w.show()
    w.eq_panel.select_presets(["builtin:hum_50", "builtin:voice_clarity"])
    w.dyn_panel.comp_on.setChecked(True)           # show the compressor at work
    from noise_filter.ui.widgets import IconButton
    # look like a running filter (demo mode feeds the pipeline without an audio device)
    w.start_btn.setEnabled(True)
    w.start_btn.blockSignals(True); w.start_btn.setChecked(True); w.start_btn.blockSignals(False)
    w.start_btn.setText(tr("engine.stop", w.lang))
    IconButton.set(w.start_btn, "stop", "#ffffff", size=18)

    def settle(ms: int = 1500):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def shot(name: str, tab: int, mode: str):
        theme.apply(mode)
        w.tabs.setCurrentIndex(tab)
        settle()
        w.state_lbl.setText(tr("status.running", w.lang))   # demo badge -> "Running"
        w.status.setText("")
        settle(100)
        w.grab().save(str(OUT / f"{name}.png"))
        print("wrote", OUT / f"{name}.png")

    OUT.mkdir(parents=True, exist_ok=True)
    settle(2500)                     # let the spectrum averages fill up
    shot("hero", 0, "light")
    shot("equalizer", 1, "light")
    shot("dynamics", 2, "light")
    shot("settings", 3, "light")
    shot("dark", 1, "dark")
    shot("hero-dark", 0, "dark")
    w._quitting = True
    w.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
