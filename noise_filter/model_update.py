"""AI model management: bundled model, downloaded updates, and the update check.

Where models live
  - bundled:    noise_filter/models/manifest.json + nfnet-<version>.onnx (ships in the installer, works offline)
  - downloaded: %APPDATA%/NoiseFilter/models/ (newer models fetched by the update check)

Update check
  The app reads manifest.json from the repository's default branch over HTTPS. If it lists a newer
  model that this app version supports, the model file is downloaded next to the manifest URL,
  its size and SHA-256 are verified, and only then is it moved into place. No internet = no
  change, the app keeps using what it has. Nothing is uploaded.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import urllib.parse
import urllib.request
from importlib import resources
from pathlib import Path

from . import __version__

MANIFEST_URL = os.environ.get(
    "NF_MODEL_MANIFEST_URL",
    "https://raw.githubusercontent.com/SkillsHUB-Electronics/Noise-Filter/HEAD/noise_filter/models/manifest.json")
ALLOWED_PREFIXES = ("https://raw.githubusercontent.com/SkillsHUB-Electronics/",
                    "https://github.com/SkillsHUB-Electronics/")
MAX_MODEL_BYTES = 50 * 1024 * 1024


def _ver(v: str) -> tuple:
    out = []
    for part in str(v).replace("-", ".").split("."):
        out.append(int(part) if part.isdigit() else 0)
    return tuple(out)


def user_models_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "NoiseFilter" / "models"


def _read_manifest(path: Path) -> dict | None:
    try:
        m = json.loads(path.read_text("utf-8"))
        latest = m["latest"]
        f = path.parent / latest["file"]
        if f.is_file():
            return {**latest, "path": f}
    except Exception:
        pass
    return None


def bundled_model() -> dict | None:
    try:
        d = Path(str(resources.files("noise_filter") / "models"))
    except Exception:
        return None
    return _read_manifest(d / "manifest.json")


def downloaded_model() -> dict | None:
    return _read_manifest(user_models_dir() / "manifest.json")


def current_model() -> dict | None:
    """Newest model available on this PC (downloaded or bundled), or None."""
    cands = [m for m in (downloaded_model(), bundled_model()) if m]
    return max(cands, key=lambda m: _ver(m["version"])) if cands else None


def current_model_path() -> str:
    m = current_model()
    return str(m["path"]) if m else ""


def _get(url: str, timeout: float, limit: int) -> bytes:
    if not url.startswith(ALLOWED_PREFIXES):
        raise ValueError(f"refusing to download from {url}")
    req = urllib.request.Request(url, headers={"User-Agent": f"NoiseFilter/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError("download too large")
    return data


def check_for_update(timeout: float = 6.0) -> dict | None:
    """Return the remote model entry if it is newer than what we have and supported, else None."""
    remote = json.loads(_get(MANIFEST_URL, timeout, 256 * 1024))["latest"]
    if _ver(remote.get("min_app_version", "0")) > _ver(__version__):
        return None
    cur = current_model()
    if cur and _ver(cur["version"]) >= _ver(remote["version"]):
        return None
    return remote


def download_update(remote: dict, timeout: float = 60.0) -> dict:
    """Download, verify and install a model entry from check_for_update(). Returns the installed entry."""
    name = Path(remote["file"]).name
    url = urllib.parse.urljoin(MANIFEST_URL, name)
    data = _get(url, timeout, MAX_MODEL_BYTES)
    if len(data) != int(remote["size"]) or hashlib.sha256(data).hexdigest() != remote["sha256"]:
        raise ValueError("model download failed verification (size or SHA-256 mismatch)")
    d = user_models_dir()
    d.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=d, delete=False, suffix=".part") as f:
        f.write(data)
    os.replace(f.name, d / name)
    for old in d.glob("nfnet-*.onnx"):
        if old.name != name:
            try:
                old.unlink()
            except OSError:
                pass
    (d / "manifest.json").write_text(json.dumps({"schema": 1, "latest": {k: v for k, v in remote.items()}}, indent=2))
    return {**remote, "path": d / name}


def update_in_background(on_done) -> threading.Thread:
    """Check + download in a daemon thread. on_done(installed_entry_or_None, error_or_None) is
    called from that thread; the UI must hop back to its own thread before touching widgets."""
    def work():
        try:
            remote = check_for_update()
            on_done(download_update(remote) if remote else None, None)
        except Exception as e:  # offline, GitHub unreachable, bad file: keep the current model
            on_done(None, e)
    t = threading.Thread(target=work, daemon=True, name="model-update")
    t.start()
    return t
