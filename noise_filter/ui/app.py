import sys


def app_icon(QtGui):
    """Logo at every size: full logo when large, the waveform mark when small."""
    from importlib import resources
    from PySide6.QtCore import Qt
    assets = resources.files("noise_filter.assets")
    icon = QtGui.QIcon()
    for name, sizes in (("icon_small.png", (16, 24, 32, 48)), ("icon.png", (64, 128, 256, 512))):
        pix = QtGui.QPixmap()
        pix.loadFromData(assets.joinpath(name).read_bytes())
        for s in sizes:
            icon.addPixmap(pix.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    return icon


def run(demo: bool = False) -> int:
    from PySide6 import QtWidgets as W
    import pyqtgraph as pg
    pg.setConfigOptions(antialias=True)
    from PySide6 import QtGui
    if sys.platform == "win32":   # own taskbar icon instead of python.exe's
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SkillsHUB.NoiseFilter")
    app = W.QApplication.instance() or W.QApplication(sys.argv)
    app.setApplicationName("Noise Filter")
    app.setWindowIcon(app_icon(QtGui))
    from .main_window import MainWindow
    w = MainWindow(demo=demo)
    w.resize(1100, 720)
    w.show()
    return app.exec()
