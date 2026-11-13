"""Quality gate + publish: copy a trained model into noise_filter/models/ and update manifest.json.

    python -m training.publish runs/latest noise_filter/models [data/contrib/contrib_report.json]
    # exit code 1 = not published

The model is published only when it beats the spectral DSP baseline and is not worse than
the model that ships today (scored on the same mixtures by train.py). Merging the branch that
contains the new files ships the model: apps read the manifest from the default branch.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

MIN_APP_VERSION = "0.3.0"


def passes(m: dict) -> tuple[bool, str]:
    new, dsp = m["nfnet"], m["spectral"]
    pesq_new, pesq_dsp = new.get("pesq") or 0, dsp.get("pesq") or 0
    if not (new["si_sdr"] > dsp["si_sdr"] and new["stoi"] >= dsp["stoi"] - 0.005 and pesq_new >= pesq_dsp):
        return False, "does not beat the spectral DSP baseline"
    if new["ms_per_frame"] > 5.0:
        return False, f"too slow ({new['ms_per_frame']:.2f} ms per frame)"
    cur = m.get("current")
    if cur:
        score = lambda r: r["si_sdr"] + 10 * r["stoi"] + 2 * (r.get("pesq") or 0)
        if score(new) < score(cur):
            return False, f"not better than shipped model {cur.get('version')}"
    return True, "ok"


def publish(run_dir: Path, models_dir: Path, contrib_report: Path | None = None) -> bool:
    meta = json.loads((run_dir / "model.json").read_text())
    ok, why = passes(meta["metrics"])
    print(f"quality gate: {why}")
    if not ok:
        return False
    models_dir.mkdir(parents=True, exist_ok=True)
    name = f"nfnet-{meta['version']}.onnx"
    for old in models_dir.glob("nfnet-*.onnx"):   # git history keeps older models
        old.unlink()
    shutil.copy(run_dir / "model.onnx", models_dir / name)
    keep = ("si_sdr", "stoi", "pesq", "residual_db", "ms_per_frame")
    manifest = {
        "schema": 1,
        "latest": {
            "name": "nfnet", "version": meta["version"], "file": name, "sha256": meta["sha256"],
            "size": (models_dir / name).stat().st_size, "min_app_version": MIN_APP_VERSION,
            "published": time.strftime("%Y-%m-%d"),
            "metrics": {k: {m: round(v, 4) for m, v in meta["metrics"][k].items() if m in keep and v is not None}
                        for k in ("noisy", "spectral", "nfnet")},
        },
    }
    if contrib_report and contrib_report.is_file():   # lets the weekly run skip when nothing new arrived
        manifest["latest"]["contrib_samples"] = int(json.loads(contrib_report.read_text()).get("accepted_total", 0))
    (models_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"published {name}")
    return True


if __name__ == "__main__":
    report = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    sys.exit(0 if publish(Path(sys.argv[1]), Path(sys.argv[2]), report) else 1)
