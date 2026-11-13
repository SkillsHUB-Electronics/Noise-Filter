# Noise Filter

Realtime, low-latency microphone noise filter for Windows with input/output frequency analyzer
and an AI (ONNX) denoiser that can be trained offline. English is the primary language, Bahasa Indonesia supported.

```
Mic (any input device) -> [highpass -> denoise -> gate -> gain] -> virtual mic (VB-Cable) -> TeamTalk / Meet / ...
                              \-> input & output spectrum analyzers
```

## Status
Implemented: framed DSP core (10 ms frames @ 48 kHz), spectral denoiser (adaptive or learned noise profile),
noise gate, high-pass, spectrum analyzer, ONNX denoiser wrapper, WASAPI device listing, realtime engine, CLI, EN/ID strings, tests.
Qt UI (PySide6 + pyqtgraph): device pickers, live input/output spectrum, level meters, filter controls, learn-room-noise, EN/ID, saved settings. `noise-filter ui` (add `--demo` for a synthetic signal).
C++ core (`cpp/`, nf-core): 1:1 port of `core/` with a native WASAPI engine and a C API. The app uses it
automatically when the DLL is built (about 15x cheaper DSP, audio thread free of Python). See [cpp/README.md](cpp/README.md).
AI denoiser (`training/`, NFNet): small realtime model (0.4 ms per 10 ms frame in C++), trained in GitHub Actions
on public 48 kHz data, shipped with the installer and updated automatically (verified download, live swap). See
[training/README.md](training/README.md).
Background use (0.5.0): system-tray icon (show/hide, filter on/off, quit; green dot while filtering), settings for
"keep running in the tray when closed", "start with Windows" (per-user `HKCU\...\Run`, opens hidden with
`noise-filter ui --minimized`) and "turn the filter back on at launch". Every setting, the devices and the window size
are remembered in `%APPDATA%\NoiseFilter\config.json`; only one instance runs (opening it again shows the window).

## Low latency design
- Fixed 480-sample frames (10 ms). Spectral denoiser adds 1 frame of algorithmic delay.
- `core/` has no UI/device imports and works on one frame at a time; `cpp/` is its 1:1 C++ port (ONNX models are reused as-is).
- Measured DSP cost per 10 ms frame: ~0.45 ms in Python, ~0.02 ms in C++. Use `--exclusive` (WASAPI exclusive) for the lowest device latency.
- Inference is CPU-only; a GPU is only needed for training.

## Usage (Windows)
```
pip install -e .[audio,ai,ui]
cmake -S cpp -B cpp/build -A x64 && cmake --build cpp/build --config Release && cmake --install cpp/build --config Release
noise-filter ui          # graphical app (uses the C++ engine if built, else Python)
noise-filter devices
noise-filter run --in <id> --out <id of "CABLE Input"> [--exclusive]
```
Then pick "CABLE Output" as the microphone in your app. VB-Cable must be installed separately.

## Tests
```
pip install -e .[dev] && pytest
```

## Windows installer (offline)
CI builds `NoiseFilter-Setup-<version>.exe`: the app frozen with PyInstaller (Python, Qt and nf-core inside, nothing to
download) plus VB-CABLE, which it installs silently if it is not there yet. Publishing a GitHub release attaches the
installer to it automatically. Build locally on Windows: `pyinstaller packaging/windows/noise_filter.spec`, extract the VB-CABLE driver pack to
`build/vbcable/`, then `iscc packaging/windows/installer.iss`.

VB-CABLE is made by VB-Audio (www.vb-cable.com) and is bundled under their distribution terms.
VB-CABLE is a donationware, all participations are welcome. Deployments in companies, schools or public institutions,
where end users cannot donate themselves, need VB-CABLE licenses bought by the distributor.
