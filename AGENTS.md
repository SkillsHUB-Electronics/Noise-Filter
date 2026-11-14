# Instructions for AI agents

Read [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/architecture.md](docs/architecture.md) first. The
rules there apply to agents too. The points that are easy to miss:

- **Default branch** is `ccr-b550d426-d4tmx2`. Work on a feature branch and open a pull request.
- **Python ↔ C++ parity.** `noise_filter/core/` is the reference; `cpp/src/` must match it.
  `tests/test_native_parity.py` checks this on CI (Windows and Linux).
- **Legal files.** `noise_filter/legal/` is the source of truth. The root `LICENSE`, `PRIVACY.md`
  and `THIRD_PARTY_NOTICES.md` must be byte-identical copies (`tests/test_legal.py`). Any new data
  the app sends must be added to both privacy policies (English and Bahasa Indonesia).
- **Two languages.** Every UI string goes into `noise_filter/i18n/en.json` and `id.json`.
- **Version** lives in `pyproject.toml` and `noise_filter/__init__.py`; bump both together and add a
  CHANGELOG entry ([docs/releasing.md](docs/releasing.md)).
- **Screenshots.** After a visible UI change, run `python tools/readme_screenshots.py` and commit
  the PNGs in `docs/images/`.
- **Releases** are published by a maintainer; agents prepare the notes but do not create tags.
- **Report only what ran.** Say which tests you ran and which you could not run (for example the
  Windows-only WASAPI engine), and rely on CI for the rest.
