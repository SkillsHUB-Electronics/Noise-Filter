import sys


def run(demo: bool = False) -> int:
    from PySide6 import QtWidgets as W
    import pyqtgraph as pg
    pg.setConfigOptions(antialias=True)
    app = W.QApplication.instance() or W.QApplication(sys.argv)
    from .main_window import MainWindow
    w = MainWindow(demo=demo)
    w.resize(1100, 720)
    w.show()
    return app.exec()
