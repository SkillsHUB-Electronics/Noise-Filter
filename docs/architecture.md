# Architecture

Noise Filter is a Windows desktop app with a realtime audio core. Python is the reference
implementation and the UI; C++ runs the audio in production. Both process the same 10 ms frames
and are checked against each other sample by sample.

## Signal chain

```
Microphone
   │  WASAPI capture (shared or exclusive), 48 kHz mono float
   ▼
high-pass ─▶ denoise ─▶ EQ ─▶ gate ─▶ compressor ─▶ output gain ─▶ limiter
   │            │                                                     │
   │            └ spectral (adaptive or learned profile) or NFNet ONNX │
   ▼                                                                  ▼
input analyzer                                               output analyzer
(spectrum, level)                                            (spectrum, level)
                                                                      │
                                                   WASAPI render ─▶ CABLE Input ─▶ CABLE Output ─▶ meeting app
```

- **Frame size:** 480 samples (10 ms at 48 kHz). The spectral and AI denoisers add one frame of
  algorithmic delay; the EQ, gate, compressor and limiter add none.
- **Cost per frame:** about 0.45 ms in Python and about 0.02 ms in C++; NFNet adds about 0.4 ms in C++.
- **Inference is CPU-only.** A GPU is only useful for training.

## Components

| Layer | Path | Notes |
|---|---|---|
| Python core | `noise_filter/core/` | `pipeline.py` (chain), `spectral.py`, `denoiser_onnx.py`, `eq.py` + `biquad.py`, `dynamics.py`, `gate.py`, `analyzer.py`. No UI or device imports, one frame at a time |
| C++ core | `cpp/` | nf-core: 1:1 C++17 port, event-driven WASAPI engine with MMCSS "Pro Audio" priority, C API in `include/nf/nf.h`, `nf-cli`. See [cpp/README.md](../cpp/README.md) |
| Bridge | `noise_filter/core/native.py` | Loads `nf_core.dll` with ctypes; falls back to Python when it is missing or `NF_CORE_DISABLE=1` |
| Audio (Python) | `noise_filter/audio/` | sounddevice engine and device list, used when the C++ core is not built |
| Desktop app | `noise_filter/ui/` | PySide6 + pyqtgraph: `main_window.py`, `eq_panel.py`, `dynamics_panel.py`, `theme.py`, tray, `settings.py` (`%APPDATA%\NoiseFilter\config.json`) |
| Strings | `noise_filter/i18n/` | `en.json` (primary) and `id.json` |
| Control | `noise_filter/remote.py`, `ctl.py`, `mcp_server.py`, `ui/control_server.py` | Per-user named pipe, `nfctl`, MCP server. See [control.md](control.md) |
| AI model | `training/`, `noise_filter/models/`, `noise_filter/model_update.py` | NFNet training in CI; bundled model plus verified updates |
| Noise samples | `noise_filter/contribute.py`, `cloud/worker/` | Opt-in upload, Cloudflare Worker + R2, review page |
| Legal | `noise_filter/legal/` | Source of truth for LICENSE, PRIVACY and THIRD_PARTY_NOTICES (root copies must match) |
| Packaging | `packaging/windows/` | PyInstaller spec, Inno Setup script, `nfctl` launcher, VB-CABLE notice |

## Threads

- **Audio thread** (C++): waits on both WASAPI device events and runs the chain. Settings, learned
  noise and model swaps are handed over with `try_lock`, so the UI can never block audio.
- **UI thread** (Qt): reads analyzer spectra about 30 times a second and draws them.
- **Background workers**: model update check, sample upload, control-pipe server.

## AI model updates

```
GitHub Actions (train.yml, weekly or on demand)
   └─▶ train ─▶ evaluate vs spectral DSP and vs the shipped model ─▶ quality gate
          └─▶ commit nfnet-<version>.onnx + manifest.json to noise_filter/models/
App start
   └─▶ read manifest.json from the default branch over HTTPS
          └─▶ newer and supported? download, verify size and SHA-256, swap the model live
```

## Noise sample pipeline

```
App (opt-in) ─▶ on-device voice / clipping / silence check ─▶ POST /v1/samples ─▶ R2 incoming/
CI daily (screen-samples.yml) ─▶ review/ or rejected/
Developer on /review           ─▶ accepted/ (used for training) or rejected/
Weekly training                ─▶ uses accepted/ only
```

The Worker stores no IP address. Users can delete all their samples from Settings. What is sent is
listed in the [privacy policy](../PRIVACY.md) and enforced by `tests/test_contribute.py`.
