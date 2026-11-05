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
Next: Qt UI with analyzer plots, training pipeline (`training/`), packaging.

## Low latency design
- Fixed 480-sample frames (10 ms). Spectral denoiser adds 1 frame of algorithmic delay.
- `core/` has no UI/device imports and works on one frame at a time, so it ports 1:1 to C++ (ONNX models are reused as-is).
- Measured DSP cost: ~0.45 ms per 10 ms frame in Python. Use `--exclusive` (WASAPI exclusive) for the lowest device latency.
- Inference is CPU-only; a GPU is only needed for training.

## Usage (Windows)
```
pip install -e .[audio,ai]
noise-filter devices
noise-filter run --in <id> --out <id of "CABLE Input"> [--exclusive]
```
Then pick "CABLE Output" as the microphone in your app. VB-Cable must be installed separately.

## Tests
```
pip install -e .[dev] && pytest
```
