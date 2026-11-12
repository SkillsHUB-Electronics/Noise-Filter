"""Model manager: bundled vs downloaded model, update check, verification."""
import hashlib
import json

import pytest

from noise_filter import model_update as mu


def _write_models(d, version, payload=b"onnx-bytes"):
    d.mkdir(parents=True, exist_ok=True)
    name = f"nfnet-{version}.onnx"
    (d / name).write_bytes(payload)
    entry = {"name": "nfnet", "version": version, "file": name, "size": len(payload),
             "sha256": hashlib.sha256(payload).hexdigest(), "min_app_version": "0.0.1"}
    (d / "manifest.json").write_text(json.dumps({"schema": 1, "latest": entry}))
    return entry


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    bundled = tmp_path / "bundled"
    monkeypatch.setattr(mu, "bundled_model", lambda: mu._read_manifest(bundled / "manifest.json"))
    return tmp_path, bundled


def test_version_order():
    assert mu._ver("2026.11.12") > mu._ver("2026.2.1")
    assert mu._ver("0.3.0") > mu._ver("0.2.9")


def test_current_prefers_newest(env):
    tmp, bundled = env
    assert mu.current_model() is None and mu.current_model_path() == ""
    _write_models(bundled, "2026.01.01")
    assert mu.current_model()["version"] == "2026.01.01"
    _write_models(mu.user_models_dir(), "2026.02.01")
    assert mu.current_model()["version"] == "2026.02.01"


def test_update_download_and_verify(env, monkeypatch):
    tmp, bundled = env
    _write_models(bundled, "2026.01.01")
    payload = b"new-model" * 100
    remote = _write_models(tmp / "remote", "2026.03.01", payload)
    files = {mu.MANIFEST_URL: json.dumps({"schema": 1, "latest": remote}).encode(),
             mu.MANIFEST_URL.rsplit("/", 1)[0] + "/" + remote["file"]: payload}
    monkeypatch.setattr(mu, "_get", lambda url, timeout, limit: files[url])
    r = mu.check_for_update()
    assert r["version"] == "2026.03.01"
    got = mu.download_update(r)
    assert got["path"].read_bytes() == payload
    assert mu.current_model()["version"] == "2026.03.01"
    assert mu.check_for_update() is None            # now up to date


def test_tampered_model_is_rejected(env, monkeypatch):
    tmp, _ = env
    remote = _write_models(tmp / "remote", "2026.03.01", b"good")
    monkeypatch.setattr(mu, "_get", lambda url, timeout, limit: b"evil" if url.endswith(".onnx") else
                        json.dumps({"latest": remote}).encode())
    with pytest.raises(ValueError):
        mu.download_update(mu.check_for_update())
    assert mu.downloaded_model() is None


def test_newer_app_required(env, monkeypatch):
    tmp, _ = env
    remote = _write_models(tmp / "remote", "2026.03.01")
    remote["min_app_version"] = "99.0"
    monkeypatch.setattr(mu, "_get", lambda *a: json.dumps({"latest": remote}).encode())
    assert mu.check_for_update() is None


def test_only_trusted_hosts():
    with pytest.raises(ValueError):
        mu._get("https://example.com/model.onnx", 1, 10)
