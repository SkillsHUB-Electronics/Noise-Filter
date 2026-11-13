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


def _server_name() -> str:
    import getpass
    try:
        user = getpass.getuser()
    except Exception:
        user = "user"
    return f"SkillsHUB.NoiseFilter.{user}"


def _ask_running_instance(name: str) -> bool:
    """True when another Noise Filter is already open; it is asked to show its window."""
    from PySide6.QtNetwork import QLocalSocket
    sock = QLocalSocket()
    sock.connectToServer(name)
    if not sock.waitForConnected(300):
        return False
    sock.write(b"show\n"); sock.flush(); sock.waitForBytesWritten(300)
    sock.disconnectFromServer()
    return True


def _listen(name: str, on_show):
    from PySide6.QtNetwork import QLocalServer
    server = QLocalServer()
    if not server.listen(name):          # stale socket after a crash (Unix)
        QLocalServer.removeServer(name)
        server.listen(name)

    def accept():
        while server.hasPendingConnections():
            c = server.nextPendingConnection()
            c.readyRead.connect(on_show)
            c.disconnected.connect(c.deleteLater)
    server.newConnection.connect(accept)
    return server


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
    name = _server_name()
    if not demo and _ask_running_instance(name):
        return 0                           # one instance only: two would fight over the microphone
    from .main_window import MainWindow
    w = MainWindow(demo=demo)
    server = _listen(name, w.show_window) if not demo else None   # noqa: F841 (kept alive)
    if minimized and w.tray.isVisible():
        pass                               # start-up with Windows: stay in the tray
    elif minimized:
        w.showMinimized()
    else:
        w.show()
    return app.exec()
