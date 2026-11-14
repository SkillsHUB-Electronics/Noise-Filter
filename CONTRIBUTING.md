# Contributing to Noise Filter

Thanks for helping make voices clearer. Bug reports, ideas, documentation fixes and code are all
welcome. Issues may be written in English or Bahasa Indonesia; code, comments and docs are in English.

## Ways to help

- **Report a bug** with the [bug report form](https://github.com/SkillsHUB-Electronics/Noise-Filter/issues/new?template=bug_report.yml).
  Include the version (Settings › About), Windows version, devices, and `nfctl status` output.
- **Suggest a feature** with the [feature request form](https://github.com/SkillsHUB-Electronics/Noise-Filter/issues/new?template=feature_request.yml).
- **Share room noise** from the app (Settings › *Send a noise file…*). It directly improves the AI model.
- **Send a pull request** for an open issue, or open an issue first for anything larger than a small fix.

Security problems go through [SECURITY.md](SECURITY.md), not public issues.

## Development setup

```powershell
git clone https://github.com/SkillsHUB-Electronics/Noise-Filter
cd Noise-Filter
pip install -e .[audio,ai,ui,dev]
pytest
noise-filter ui --demo
```

Building the C++ core and the installer: [docs/building.md](docs/building.md).
How the pieces fit together: [docs/architecture.md](docs/architecture.md).

## Pull request checklist

1. **Branch from the default branch** and keep the change focused on one thing.
2. **Keep Python and C++ in step.** A change to `noise_filter/core/` needs the same change in
   `cpp/src/`; `tests/test_native_parity.py` compares them sample by sample.
3. **Keep the audio path realtime-safe.** No allocation, locks that can block, file or network I/O
   on the audio thread. Anything new in the chain must fit in a 10 ms frame with room to spare.
4. **Add or update tests** that fail without your change (`tests/`, `cpp/tests/`, `cloud/worker/test/`).
5. **Translate new UI text** in both `noise_filter/i18n/en.json` and `id.json`.
6. **Update the privacy policy** in `noise_filter/legal/` (and the root copy) if the app sends any
   new data. `tests/test_legal.py` checks that root copies match and that uploaded fields are listed.
7. **Update the docs**: README or `docs/` for user-visible changes, an entry under *Unreleased* in
   [CHANGELOG.md](CHANGELOG.md), and new screenshots with `python tools/readme_screenshots.py` when
   the UI changes.
8. **CI must pass** before review.

## Style

- Python 3.10+, standard library style, type hints on public functions, short docstrings that say why.
- C++17, no exceptions across the C API, no heap allocation in per-frame code.
- Commit messages: a short imperative summary (`Add notch preset for 60 Hz hum`), details in the body.

## Licensing

By contributing you agree that your contribution is licensed under the [MIT License](LICENSE).
Only add dependencies, data or assets whose license allows redistribution in the installer, and list
them in `noise_filter/legal/THIRD_PARTY_NOTICES.md`.
