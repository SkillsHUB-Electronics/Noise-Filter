# nf-core (C++)

Realtime core of Noise Filter: a 1:1 C++17 port of `noise_filter/core` plus a native
Windows (WASAPI) audio engine, behind a small C API (`include/nf/nf.h`). The same
library will be used by the desktop app now and by the Android/iOS apps later.

```
mic -> [WASAPI capture] -> highpass -> denoise (spectral | ONNX) -> gate -> gain -> [WASAPI render] -> VB-Cable
                             \-> input / output analyzers (read by the UI without blocking audio)
```

## What you get
| File | Purpose |
|---|---|
| `nf_core.dll` / `libnf_core.so` | Shared library, loaded by the Python app via ctypes (`noise_filter/core/native.py`) |
| `nf-cli` | Command line: `devices`, `run`, `process in.wav out.wav`, `bench` |
| `nf_tests` | C++ tests (same behaviour checks as `tests/test_core.py`) |

Measured: about 15 to 20 µs per 10 ms frame for the full chain (Python: about 0.45 to 0.8 ms).
Output matches the Python reference to about 1e-7 (checked by `tests/test_native_parity.py`).

## Build (Windows, Visual Studio 2022 or Build Tools)
```
cmake -S cpp -B cpp/build -A x64
cmake --build cpp/build --config Release
ctest --test-dir cpp/build -C Release
cmake --install cpp/build --config Release     # copies nf_core.dll + nf-cli.exe to noise_filter/_native/
```
After the install step, `noise-filter ui` uses the C++ engine automatically (the status bar
shows "Engine: C++"). Delete `noise_filter/_native/` or set `NF_CORE_DISABLE=1` to go back
to the Python engine.

MinGW-w64 works too (`cmake -G "MinGW Makefiles" ...`); the DLL is linked statically so it
needs no runtime DLLs next to it.

## Run from the command line
```
noise_filter\_native\nf-cli devices
noise_filter\_native\nf-cli run --in "Microphone" --out "CABLE Input"          # names or indices
noise_filter\_native\nf-cli run --in 0 --out "CABLE Input" --exclusive          # lowest latency
noise_filter\_native\nf-cli process noisy.wav clean.wav --learn-seconds 1       # 48 kHz WAV
```
`run` prints frames, xruns, DSP time and the estimated end-to-end latency every second.

## ONNX denoiser (optional)
Download an ONNX Runtime release (for example `onnxruntime-win-x64-1.20.1.zip`), then:
```
cmake -S cpp -B cpp/build -A x64 -DNF_WITH_ONNX=ON -DONNXRUNTIME_DIR=C:/path/to/onnxruntime-win-x64-1.20.1
```
Copy `onnxruntime.dll` next to `nf_core.dll`. Model contract (same as Python):
input `frame` float32 `[1, 480]`, output `frame_out` float32 `[1, 480]` (older models may call it
`frame`), and recurrent state as inputs `state*` fed from outputs `state*`, paired in order.

## Engine design (Windows)
- One thread with MMCSS "Pro Audio" priority waits on both device events (event-driven WASAPI).
- Shared mode asks Windows for mono float 48 kHz (auto-convert); exclusive mode picks a 48 kHz
  format the hardware accepts (float / 16 / 24 / 32-bit, mono or stereo) and the smallest period >= 3 ms.
- The output queue is kept near one frame. Clock drift between two devices is absorbed by
  dropping or padding samples, counted as xruns.
- Settings, noise learning and model swaps are handed to the audio thread with `try_lock`,
  so the UI can never block audio. Analyzer spectra are computed on the UI thread.

## Layout
```
include/nf/nf.h          C API (stable ABI for Python ctypes now, Flutter dart:ffi later)
src/core.hpp, dsp.cpp    FFT wrapper, high-pass, gate, spectral denoiser, analyzer
src/pipeline.cpp         processing chain
src/onnx_denoiser.cpp    ONNX Runtime wrapper (compiled only with NF_WITH_ONNX)
src/capi.cpp             C API + thread hand-off
src/engine_wasapi.cpp    Windows engine and device list; engine_stub.cpp elsewhere
third_party/pocketfft    header-only FFT (BSD-3-Clause)
```
