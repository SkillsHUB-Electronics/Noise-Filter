"""Screen user-contributed noise samples in R2 and fetch the accepted ones for training (F3).

    python -m training.contrib_samples --out data/contrib --base-noise data/noise   # training
    python -m training.contrib_samples --screen-only                                # daily screening

Bucket layout (written by cloud/worker):
    incoming/<install_id>/<date>-<uuid>.wav    new, unscreened
    review/<install_id>/<date>-<uuid>.wav      passed screening, waits for the developer (/review page)
    accepted/<install_id>/<date>-<uuid>.wav    accepted by the developer, used for training
    rejected/<install_id>/<date>-<uuid>.wav    failed screening or rejected by the developer (reason in
                                               metadata), deleted after 30 days

Only accepted/ reaches training, and only a person can put a sample there: an accepted/ sample
without the "reviewed" mark (from before the review step existed) is sent back to review/.

Screening repeats the app's checks (format, length, clipping, silence, voice detection with the
heuristic AND the current AI model), drops exact duplicates and caps how many samples one
installation can add per day. Fetching caps each installation at 2 % of the accepted pool and
the whole pool at the size of the base noise set, so no single source dominates training.

Needs R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY and CLOUDFLARE_ACCOUNT_ID in the environment.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import random
import wave
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

BUCKET = "nf-noise"
DAILY_CAP = 20          # accepted samples per installation per day
INSTALL_SHARE = 0.02    # max share of the fetched pool from one installation (at least 5 files)
REJECT_KEEP_DAYS = 30


def client():
    import boto3
    acc = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    return boto3.client(
        "s3", endpoint_url=f"https://{acc}.r2.cloudflarestorage.com", region_name="auto",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])


def list_keys(s3, prefix: str):
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix):
        for o in page.get("Contents", []):
            yield o


def read_wav(data: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(data)) as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, 48000):
            raise ValueError("not 48 kHz mono 16-bit")
        return np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768.0


def install_of(key: str) -> str:
    return key.split("/")[1]


def day_of(key: str) -> str:
    return key.split("/")[2][:10]


def screen(data: bytes, model_path: str | None) -> tuple[bool, str]:
    from noise_filter.contribute import check_sample
    try:
        x = read_wav(data)
    except Exception as e:
        return False, f"bad wav: {e}"
    if len(x) > 10.5 * 48000:
        return False, "too long"
    return check_sample(x, model_path)


def move(s3, key: str, dest_prefix: str, meta: dict):
    new = dest_prefix + key.split("/", 1)[1]
    s3.copy_object(Bucket=BUCKET, Key=new, CopySource={"Bucket": BUCKET, "Key": key},
                   Metadata=meta, MetadataDirective="REPLACE", ContentType="audio/wav")
    s3.delete_object(Bucket=BUCKET, Key=key)
    return new


def requeue_unreviewed(s3) -> int:
    """accepted/ samples nobody reviewed (screened before the review step existed) go back to review/."""
    n = 0
    for o in list(list_keys(s3, "accepted/")):
        meta = dict(s3.head_object(Bucket=BUCKET, Key=o["Key"]).get("Metadata", {}))
        if not meta.get("reviewed"):
            move(s3, o["Key"], "review/", meta)
            n += 1
    return n


def process_incoming(s3, model_path: str | None) -> dict:
    """Screen incoming/ into review/ (waits for the developer) or rejected/. Returns counts."""
    seen = set()
    per_day = defaultdict(int)
    for prefix in ("review/", "accepted/"):              # existing hashes and daily counts
        for o in list_keys(s3, prefix):
            head = s3.head_object(Bucket=BUCKET, Key=o["Key"])
            if "sha256" in head.get("Metadata", {}):
                seen.add(head["Metadata"]["sha256"])
            per_day[(install_of(o["Key"]), day_of(o["Key"]))] += 1
    stats = defaultdict(int)
    for o in sorted(list_keys(s3, "incoming/"), key=lambda o: o["Key"]):
        key = o["Key"]
        obj = s3.get_object(Bucket=BUCKET, Key=key)
        data, meta = obj["Body"].read(), dict(obj.get("Metadata", {}))
        digest = hashlib.sha256(data).hexdigest()
        ok, reason = screen(data, model_path)
        if ok and digest in seen:
            ok, reason = False, "duplicate"
        slot = (install_of(key), day_of(key))
        if ok and per_day[slot] >= DAILY_CAP:
            ok, reason = False, "daily cap"
        meta.update(sha256=digest, screened=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    reason=reason)
        move(s3, key, "review/" if ok else "rejected/", meta)
        if ok:
            seen.add(digest)
            per_day[slot] += 1
        stats["to_review" if ok else f"rejected:{reason}"] += 1
    return dict(stats)


def purge_rejected(s3, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    old = [o["Key"] for o in list_keys(s3, "rejected/")
           if o["LastModified"] < now - timedelta(days=REJECT_KEEP_DAYS)]
    for i in range(0, len(old), 1000):
        s3.delete_objects(Bucket=BUCKET, Delete={"Objects": [{"Key": k} for k in old[i:i + 1000]]})
    return len(old)


def select_for_training(keys: list[str], limit: int, seed: int = 0) -> list[str]:
    """Cap each installation at INSTALL_SHARE of the pool (min 5 files) and the pool at `limit`."""
    rng = random.Random(seed)
    by_install = defaultdict(list)
    for k in keys:
        by_install[install_of(k)].append(k)
    total = min(len(keys), limit)
    cap = max(5, int(INSTALL_SHARE * total))
    pool = []
    for ks in by_install.values():
        rng.shuffle(ks)
        pool += ks[:cap]
    rng.shuffle(pool)
    return sorted(pool[:limit])


def count_audio(d: str | None) -> int:
    if not d or not Path(d).is_dir():
        return 0
    return sum(1 for p in Path(d).rglob("*") if p.suffix.lower() in {".wav", ".flac", ".ogg"})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/contrib")
    ap.add_argument("--base-noise", help="base noise folder: the contributed pool is capped at its size")
    ap.add_argument("--model", help="ONNX model for the voice check (default: the bundled model)")
    ap.add_argument("--no-screen", action="store_true", help="only fetch accepted/")
    ap.add_argument("--screen-only", action="store_true", help="screen incoming/ into review/, fetch nothing")
    a = ap.parse_args(argv)
    s3 = client()
    model = a.model
    if not model and not a.no_screen:
        from noise_filter.model_update import bundled_model
        m = bundled_model()
        model = str(m["path"]) if m else None
    report = {"requeued_unreviewed": requeue_unreviewed(s3),
              "screening": {} if a.no_screen else process_incoming(s3, model)}
    report["purged_rejected"] = purge_rejected(s3)
    report["waiting_for_review"] = sum(1 for _ in list_keys(s3, "review/"))
    keys = [o["Key"] for o in list_keys(s3, "accepted/")]
    if a.screen_only:
        report["accepted_total"] = len(keys)
        print(json.dumps(report, indent=2))
        return report
    limit = count_audio(a.base_noise) or len(keys)
    chosen = select_for_training(keys, limit)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for k in chosen:
        dest = out / k.replace("/", "_")
        if not dest.exists():
            s3.download_file(BUCKET, k, str(dest))
    report.update(accepted_total=len(keys), installations=len({install_of(k) for k in keys}),
                  used_for_training=len(chosen))
    (out / "contrib_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
