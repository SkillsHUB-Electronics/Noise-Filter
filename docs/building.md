# Building from source

## Requirements

- Windows 10 or 11 (the UI and the Python engine also run on Linux and macOS for development,
  without a virtual microphone)
- Python 3.10 or newer (CI uses 3.12)
- For the C++ core: Visual Studio 2022 or Build Tools with the C++ workload, and CMake 3.16+
- For a real virtual microphone: [VB-CABLE](https://www.vb-cable.com)

## Run the app

```powershell
pip install -e .[audio,ai,ui]
noise-filter ui                  # add --demo for a synthetic signal (no audio device needed)
```

Extras: `audio` = sounddevice, `ai` = ONNX Runtime, `ui` = PySide6 + pyqtgraph, `dev` = pytest + scipy.

## Build the C++ core (recommended)

```powershell
cmake -S cpp -B cpp/build -A x64
cmake --build cpp/build --config Release
ctest --test-dir cpp/build -C Release
cmake --install cpp/build --config Release     # copies nf_core.dll + nf-cli.exe to noise_filter/_native/
```

The app then uses the C++ engine automatically (status bar: *Engine: C++*). For the AI denoiser in
C++, add `-DNF_WITH_ONNX=ON -DONNXRUNTIME_DIR=<path>`; details in [cpp/README.md](../cpp/README.md).

## Run the tests

```powershell
pip install -e .[dev] onnx onnxruntime
pytest                                           # Python tests, incl. C++ ↔ Python parity when the DLL is built
ctest --test-dir cpp/build -C Release            # C++ tests
cd cloud/worker; npm test                        # Worker tests (Node 22)
```

UI tests run headless (`QT_QPA_PLATFORM=offscreen`). CI runs the Python and C++ tests on every push and pull
request ([ci.yml](../.github/workflows/ci.yml)), and the Worker tests when `cloud/worker/` changes
([worker.yml](../.github/workflows/worker.yml)).

## Build the installer

```powershell
pyinstaller packaging/windows/noise_filter.spec
# extract the VB-CABLE driver pack to build/vbcable/
iscc /DAppVersion=0.9.0 packaging/windows/installer.iss
```

The result is `dist/NoiseFilter-Setup-<version>.exe`. CI builds the same file on every push and
attaches it to a GitHub release when one is published.

## Regenerate the README screenshots

```powershell
pip install -e .[ui]
python tools/readme_screenshots.py              # writes docs/images/*.png
```

The script opens the real window offscreen in demo mode with placeholder device names, so the
screenshots are the same on every machine. Run it after any visible UI change and commit the PNGs
with the change.
