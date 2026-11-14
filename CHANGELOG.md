# Changelog

All notable changes to Noise Filter are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Downloads and full release notes are on the
[releases page](https://github.com/SkillsHUB-Electronics/Noise-Filter/releases).

## [Unreleased]

## [0.10.0] - 2026-11-14

### Added
- **Vocal / singing mode** (Filter tab): keeps the harmonics, breath and natural decay of speech
  and singing so the voice no longer sounds dry. Spectral peaks that stand out from the noise keep
  their full level, the adaptive noise estimate never climbs into them (long sung notes are no
  longer learned as noise), high frequencies are cut more gently, gains close more slowly and the
  gate is softer. With the AI model it keeps 10 % of the original sound.
- **Mix** slider (dry/wet, 0-100 %): blends the filtered sound with the time-aligned original.
  70-85 % brings back warmth while keeping most of the noise reduction.
- `nfctl set vocal_mode=on mix=0.8` and the same settings through the MCP server.
- `nf-cli --vocal --mix 0.8`; C API v3 (`nf_config.vocal_mode`, `nf_config.mix`).
- `tools/vocal_compare.py`: before/after audio and spectrum comparison.
- Tooltips on Strength, Mix and Vocal mode explaining what to change when the voice sounds dry.
- Professional repository page: new README with screenshots, `docs/` guides, changelog, roadmap,
  contributing guide, security policy, code of conduct, and issue and pull request templates.
- `tools/readme_screenshots.py` renders the README screenshots from the real app.

## [0.9.0] - 2026-11-14

### Added
- **About** card in Settings: app version, AI model version, copyright, links to GitHub and the issue tracker.
- Privacy policy in English and Bahasa Indonesia, readable in the app and in the repository.
- MIT License for the source code; the bundled AI model is for non-commercial use.
- Third-party notices for Qt/PySide6, FFmpeg, NumPy, ONNX Runtime, VB-CABLE and other components.
- The installer shows the license and installs LICENSE, PRIVACY.md and THIRD_PARTY_NOTICES.md.

## [0.8.0] - 2026-11-14

### Changed
- Full redesign: card layout, large Start/Stop button, tabs with icons, status bar with engine,
  xruns, DSP time, latency and a segmented level meter.
- Light, Dark and System themes.
- Small laptops: tabs scroll instead of being cut off (tested at 1366 × 768, 125 % scaling).

## [0.7.1] - 2026-11-14

### Added
- Per-band lock and a "Lock presets" button in the Equalizer; both are remembered.
- 13 new stackable EQ presets (warmer, brighter, presence, broadcast, less muddy, less nasal,
  de-ess, rumble, fan/AC, headset, laptop mic, online meeting, echoey room).
- Frequency accepts decimals (0.1 Hz steps).

### Fixed
- EQ band fields no longer cut off values such as `-12.5 dB`.

## [0.7.0] - 2026-11-14

### Added
- `nfctl` command line to control the running app (JSON output).
- MCP server (`nfctl mcp`) for AI apps such as Claude Desktop and Claude Code.
- Installer option to add `nfctl` to `PATH`.

## [0.6.1] - 2026-11-14

### Added
- **Record noise…** button: records 10 s of room noise, checks it on the PC, and offers to share it.

## [0.6.0] - 2026-11-13

### Added
- **Send a noise file…**: share a recording (WAV, MP3, M4A, FLAC, OGG, up to 10 min), cut into
  at most five checked 10 s clips.
- Every shared sample is reviewed by a person before it is used for training.

## [0.5.1] - 2026-11-13

### Added
- Combine several EQ presets at once; overlapping bands are merged (up to 8).

## [0.5.0] - 2026-11-13

### Added
- System-tray icon, keep running when closed, start with Windows, resume filtering at launch.
- 8-band parametric equalizer with presets and user presets.
- Compressor and zero-latency limiter.
- Tabs: Filter & Spectrum, Equalizer, Compressor & Limiter, Settings.

### Fixed
- Overlapping controls on small or scaled screens.

## [0.4.0] - 2026-11-13

### Added
- Opt-in sharing of the *Learn noise* recording to help train the AI model (Cloudflare Worker + R2).
- Weekly automatic retraining with accepted samples.

## [0.3.0] - 2026-11-13

### Added
- NFNet AI denoiser, trained in GitHub Actions, with verified automatic model updates.
- "Check for AI model update" button.

## [0.2.0-beta.1] - 2026-11-12

### Added
- nf-core: C++17 realtime core with a native WASAPI engine and C API.
- Offline Windows installer with VB-CABLE bundled.
- App icon.

[Unreleased]: https://github.com/SkillsHUB-Electronics/Noise-Filter/compare/v0.10.0...HEAD
[0.10.0]: https://github.com/SkillsHUB-Electronics/Noise-Filter/releases/tag/v0.10.0
[0.9.0]: https://github.com/SkillsHUB-Electronics/Noise-Filter/releases/tag/v0.9.0
[0.8.0]: https://github.com/SkillsHUB-Electronics/Noise-Filter/releases/tag/v0.8.0
[0.7.1]: https://github.com/SkillsHUB-Electronics/Noise-Filter/releases/tag/v0.7.1
[0.7.0]: https://github.com/SkillsHUB-Electronics/Noise-Filter/releases/tag/v0.7.0
[0.6.1]: https://github.com/SkillsHUB-Electronics/Noise-Filter/releases/tag/v0.6.1
[0.6.0]: https://github.com/SkillsHUB-Electronics/Noise-Filter/releases/tag/v0.6.0
[0.5.1]: https://github.com/SkillsHUB-Electronics/Noise-Filter/releases/tag/v0.5.1
[0.5.0]: https://github.com/SkillsHUB-Electronics/Noise-Filter/releases/tag/v0.5.0
[0.4.0]: https://github.com/SkillsHUB-Electronics/Noise-Filter/releases/tag/v0.4.0
[0.3.0]: https://github.com/SkillsHUB-Electronics/Noise-Filter/releases/tag/v0.3.0
[0.2.0-beta.1]: https://github.com/SkillsHUB-Electronics/Noise-Filter/releases/tag/v0.2.0-beta.1
