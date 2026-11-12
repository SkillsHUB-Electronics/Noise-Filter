# PyInstaller spec: bundles Python, PySide6, numpy and nf_core.dll into one folder.
# Build from the repo root:  pyinstaller packaging/windows/noise_filter.spec --noconfirm
from pathlib import Path

root = Path(SPECPATH).resolve().parents[1]
native = root / "noise_filter" / "_native"

a = Analysis(
    [str(root / "packaging" / "windows" / "launcher.py")],
    pathex=[str(root)],
    binaries=[(str(native / "nf_core.dll"), "noise_filter/_native")],
    datas=[(str(root / "noise_filter" / "i18n" / "*.json"), "noise_filter/i18n"),
           (str(native / "nf-cli.exe"), "noise_filter/_native")],
    hiddenimports=["noise_filter.ui.app", "noise_filter.audio.engine", "noise_filter.audio.devices",
                   "sounddevice", "_sounddevice_data"],
    excludes=["tkinter", "matplotlib", "scipy", "pytest", "PySide6.QtWebEngineCore",
              "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="NoiseFilter", console=False,
          icon=None, version=None)
coll = COLLECT(exe, a.binaries, a.datas, name="NoiseFilter")
