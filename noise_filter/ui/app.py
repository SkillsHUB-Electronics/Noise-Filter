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


def _ask_running_instance(name: str, show: bool = True) -> bool:
    """True when another Noise Filter is already open; it is asked to show its window."""
    from PySide6.QtNetwork import QLocalSocket
    sock = QLocalSocket()
    sock.connectToServer(name)
    if not sock.waitForConnected(300):
        return False
    if show:
        sock.write(b"show\n"); sock.flush(); sock.waitForBytesWritten(300)
    sock.disconnectFromServer()
    return True


def run(demo: bool = False, minimized: bool = False) -> int:
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
    app.setQuitOnLastWindowClosed(False)   # closing to the tray keeps the filter running
    import os
    from ..remote import server_name
    name = server_name()
    if not demo and _ask_running_instance(name, show=not minimized):
        return 0                           # one instance only: two would fight over the microphone
    from .main_window import MainWindow
    from .control_server import listen
    w = MainWindow(demo=demo)
    # local control channel for `noise-filter ctl` / the MCP server (a demo window only for tests)
    server = listen(name, w) if not demo or os.environ.get("NF_CONTROL_NAME") else None   # noqa: F841 (kept alive)
    if minimized and w.tray.isVisible():
        pass                               # start-up with Windows: stay in the tray
    elif minimized:
        w.showMinimized()
    else:
        w.show()
    return app.exec()
