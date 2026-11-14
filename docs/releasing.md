# Releasing

1. **Bump the version** in both `pyproject.toml` and `noise_filter/__init__.py` (CI reads the
   installer version from `pyproject.toml`).
2. **Update [CHANGELOG.md](../CHANGELOG.md)**: move the *Unreleased* entries under the new version
   with today's date, and add the compare link at the bottom.
3. **Merge** the pull request into the default branch. CI must be green.
4. **Publish a GitHub release** with tag `vX.Y.Z` on the default branch, title
   `Noise Filter vX.Y.Z`, and the changelog section as the notes (in English).
5. CI (`ci.yml`, `release: published`) builds `NoiseFilter-Setup-X.Y.Z.exe` and attaches it to the
   release, usually within about 15 minutes. Check that the file is there.

AI model updates do not need an app release: the weekly training workflow publishes new models
that every app downloads on its next update check.

## Versioning

[Semantic Versioning](https://semver.org/): a new feature bumps the minor version (0.9.0 → 0.10.0),
a fix bumps the patch version (0.9.0 → 0.9.1). 1.0.0 will mark the end of the beta.
