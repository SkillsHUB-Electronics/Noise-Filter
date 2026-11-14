# Roadmap

Noise Filter is in **beta**. The Windows PC app is the focus; this page says what is done, what
is being considered, and what is on hold. It is a plan, not a promise: priorities follow user
feedback, so open an [issue](https://github.com/SkillsHUB-Electronics/Noise-Filter/issues/new/choose)
if something here matters to you.

## Done

| Phase | What shipped | Version |
|---|---|---|
| F1 | C++ realtime core (nf-core), WASAPI engine, offline installer with VB-CABLE | 0.2.0 |
| F2 | NFNet AI denoiser trained in CI, verified automatic model updates | 0.3.0 |
| F3 | Opt-in noise samples: Cloudflare Worker + R2, on-device voice check, human review | 0.4.0 – 0.6.1 |
| F5 (part) | Weekly automatic retraining with accepted samples, quality gate before shipping | 0.4.0 |
| PC app | Tray, start with Windows, parametric EQ, compressor and limiter | 0.5.x |
| PC app | `nfctl` command line and MCP server | 0.7.0 |
| PC app | New design with light/dark themes, About, privacy policy, MIT license | 0.8.0 – 0.9.0 |

## Being considered

- **Stronger AI model**: better speech preservation on non-stationary noise (keyboard, voices in
  the background) at the same CPU cost.
- **Code-signed installer** so Windows SmartScreen does not warn on first run.
- **Per-app presets**: switch EQ and filter settings automatically by meeting app.
- **Automatic update of the app itself**, not only the AI model.
- **Lower total latency**: measure end-to-end latency and tune buffer sizes per device.

## On hold

- **F4: Android and iOS.** A phone app cannot offer a virtual microphone to other apps (Android
  needs root, iOS does not allow it), so a phone version could not filter meeting apps. Paused
  since 2026-11-13.
- **macOS and Linux desktop.** The core is portable, but there is no audio engine or virtual
  microphone integration for them yet.
