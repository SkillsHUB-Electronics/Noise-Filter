# PyInstaller spec: bundles Python, PySide6, numpy and nf_core.dll into one folder.
# Build from the repo root:  pyinstaller packaging/windows/noise_filter.spec --noconfirm
from pathlib import Path

root = Path(SPECPATH).resolve().parents[1]
native = root / "noise_filter" / "_native"

a = Analysis(
    [str(root / "packaging" / "windows" / "launcher.py")],
    pathex=[str(root)],
    binaries=[(str(f), "noise_filter/_native") for f in native.glob("*.dll")],   # nf_core.dll + onnxruntime.dll
    datas=[(str(root / "noise_filter" / "i18n" / "*.json"), "noise_filter/i18n"),
           (str(root / "noise_filter" / "assets" / "*.png"), "noise_filter/assets"),
           *[(str(f), "noise_filter/models") for f in (root / "noise_filter" / "models").glob("*.*")],
           (str(native / "nf-cli.exe"), "noise_filter/_native")],
    hiddenimports=["noise_filter.ui.app", "noise_filter.audio.engine", "noise_filter.audio.devices",
                   "sounddevice", "_sounddevice_data", "noise_filter.model_update",
                   "noise_filter.ui.audio_file", "PySide6.QtMultimedia"],   # MP3/M4A decoding (noise files)
    excludes=["tkinter", "matplotlib", "scipy", "pytest", "PySide6.QtWebEngineCore",
              "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml", "onnxruntime", "torch"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="NoiseFilter", console=False,
          icon=str(root / "noise_filter" / "assets" / "icon.ico"), version=None)

# nfctl.exe: the same package as a console program, so terminals, scripts and AI agents can control the
# running app (`nfctl status`, `nfctl start`, `nfctl mcp` for MCP clients). It needs no Qt.
b = Analysis(
    [str(root / "packaging" / "windows" / "nfctl.py")],
    pathex=[str(root)],
    hiddenimports=["noise_filter.ctl", "noise_filter.remote", "noise_filter.mcp_server"],
    excludes=["tkinter", "matplotlib", "scipy", "pytest", "PySide6", "pyqtgraph", "onnxruntime", "torch",
              "sounddevice"],
    noarchive=False,
)
pyz_b = PYZ(b.pure)
exe_b = EXE(pyz_b, b.scripts, [], exclude_binaries=True, name="nfctl", console=True,
            icon=str(root / "noise_filter" / "assets" / "icon.ico"), version=None)
coll = COLLECT(exe, exe_b, a.binaries, a.datas, b.binaries, b.datas, name="NoiseFilter")
