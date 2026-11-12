"""Download public 48 kHz training data and convert it to mono 16-bit 48 kHz WAV.

    python -m training.download_data --out data --speakers 8 --demand 10

Sources (check each license before using a model commercially):
  clean speech  EARS        github.com/facebookresearch/ears_dataset   CC BY-NC 4.0   48 kHz anechoic
  noise         DEMAND      zenodo.org/records/1227121                 CC BY-SA 3.0   48 kHz, channel 1 used
  noise         ESC-50      github.com/karolpiczak/ESC-50              CC BY-NC 3.0   44.1 kHz -> 48 kHz
User-contributed noise (F3) is added later as another --noise folder.
"""
from __future__ import annotations

import argparse
import io
import random
import shutil
import urllib.request
import zipfile
from math import gcd
from pathlib import Path

import numpy as np

SR = 48_000
EARS = "https://github.com/facebookresearch/ears_dataset/releases/download/dataset/p{:03d}.zip"
DEMAND = "https://zenodo.org/records/1227121/files/{}_48k.zip?download=1"
DEMAND_ENVS = ["DKITCHEN", "DLIVING", "DWASHING", "NFIELD", "NPARK", "NRIVER", "OHALLWAY", "OMEETING",
               "OOFFICE", "PCAFETER", "PRESTO", "PSTATION", "SPSQUARE", "STRAFFIC", "TBUS", "TCAR", "TMETRO"]
ESC50 = "https://github.com/karolpiczak/ESC-50/archive/refs/heads/master.zip"
ESC50_SKIP = {"crying_baby", "laughing"}   # voice-like; the model must not learn to remove voices


def fetch(url: str, dest: Path) -> Path:
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    print(f"download {url}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "noise-filter-training"})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    tmp.rename(dest)
    return dest


def to_wav48(data: bytes, out: Path, channel: int | None = None, max_seconds: float | None = None) -> bool:
    import soundfile as sf
    from scipy.signal import resample_poly
    try:
        x, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    except Exception:
        return False
    x = x[:, channel] if channel is not None else x.mean(1)
    if max_seconds:
        x = x[: int(max_seconds * sr)]
    if sr != SR:
        g = gcd(SR, sr)
        x = resample_poly(x, SR // g, sr // g)
    if len(x) < SR // 2 or np.max(np.abs(x)) < 1e-4:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), np.clip(x, -1, 1), SR, subtype="PCM_16")
    return True


def ears(out: Path, cache: Path, speakers: list[int], max_files: int):
    for spk in speakers:
        z = fetch(EARS.format(spk), cache / f"ears_p{spk:03d}.zip")
        with zipfile.ZipFile(z) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".wav")]
            # prefer read and conversational speech; skip non-verbal vocalisations
            names = [n for n in names if "nonverbal" not in n.lower()] or names
            random.Random(spk).shuffle(names)
            kept = 0
            for n in names:
                if kept >= max_files:
                    break
                if to_wav48(zf.read(n), out / f"p{spk:03d}" / Path(n).name):
                    kept += 1
        print(f"EARS p{spk:03d}: {kept} files", flush=True)
        z.unlink()  # zips are large; keep only the converted files


def demand(out: Path, cache: Path, envs: list[str]):
    for env in envs:
        z = fetch(DEMAND.format(env), cache / f"demand_{env}.zip")
        with zipfile.ZipFile(z) as zf:
            ch = [n for n in zf.namelist() if n.lower().endswith("ch01.wav")]
            for n in ch:
                to_wav48(zf.read(n), out / f"demand_{env}.wav")
        print(f"DEMAND {env}: ok", flush=True)
        z.unlink()


def esc50(out: Path, cache: Path):
    import csv
    z = fetch(ESC50, cache / "esc50.zip")
    with zipfile.ZipFile(z) as zf:
        meta = [n for n in zf.namelist() if n.endswith("meta/esc50.csv")][0]
        rows = list(csv.DictReader(io.TextIOWrapper(zf.open(meta), "utf-8")))
        root = meta.rsplit("meta/", 1)[0]
        kept = 0
        for r in rows:
            if r["category"] in ESC50_SKIP:
                continue
            if to_wav48(zf.read(f"{root}audio/{r['filename']}"), out / r["category"] / r["filename"]):
                kept += 1
    print(f"ESC-50: {kept} clips", flush=True)
    z.unlink()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data")
    ap.add_argument("--speakers", type=int, default=8, help="number of EARS speakers")
    ap.add_argument("--files-per-speaker", type=int, default=250)
    ap.add_argument("--demand", type=int, default=10, help="number of DEMAND environments")
    ap.add_argument("--no-esc50", action="store_true")
    a = ap.parse_args(argv)
    out, cache = Path(a.out), Path(a.out) / "_cache"
    rng = random.Random(0)
    spk = sorted(rng.sample(range(1, 108), a.speakers))
    ears(out / "clean" / "ears", cache, spk, a.files_per_speaker)
    demand(out / "noise" / "demand", cache, rng.sample(DEMAND_ENVS, min(a.demand, len(DEMAND_ENVS))))
    if not a.no_esc50:
        esc50(out / "noise" / "esc50", cache)
    shutil.rmtree(cache, ignore_errors=True)
    for d in ("clean", "noise"):
        files = list((out / d).rglob("*.wav"))
        secs = sum(f.stat().st_size for f in files) / (2 * SR)
        print(f"{d}: {len(files)} files, {secs / 3600:.2f} h")


if __name__ == "__main__":
    main()
