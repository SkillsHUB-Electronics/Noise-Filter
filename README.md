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
Next: training pipeline (`training/`), packaging, then the Android app on the same C++ core.

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
