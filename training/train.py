"""Train NFNet, evaluate it against the DSP baseline, and export the streaming ONNX model.

    python -m training.train --clean data/clean --noise data/noise --minutes 120 --out runs/v1
    python -m training.train --synthetic --minutes 2 --out runs/smoke      # no data needed

Runs on CPU (a GPU is used automatically when available). Output folder:
    model.onnx      streaming model for the app (C++ and Python engines)
    model.json      metadata: version, sha256, params, cost, evaluation metrics
    report.md       evaluation table: noisy vs spectral DSP vs NFNet
    best.pt         PyTorch checkpoint (resume / fine-tune with --init)
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, IterableDataset

from .data import MixConfig, build_sources, make_mix
from .model import NFNet, count_params, macs_per_frame


class MixStream(IterableDataset):
    def __init__(self, clean, noise, cfg: MixConfig, seed: int):
        self.clean, self.noise, self.cfg, self.seed = clean, noise, cfg, seed

    def __iter__(self):
        info = torch.utils.data.get_worker_info()
        rng = random.Random(self.seed + (info.id if info else 0) * 9973 + int(time.time()))
        while True:
            x, s = make_mix(self.clean, self.noise, self.cfg, rng)
            yield torch.from_numpy(x), torch.from_numpy(s)


def spectral_loss(net: NFNet, yre, yim, clean):
    sre, sim = net.stft(clean)
    def compress(re, im):
        mag = torch.sqrt(re * re + im * im + 1e-12)
        c = mag ** 0.3
        return c, c * re / mag, c * im / mag
    ym, yr, yi = compress(yre, yim)
    sm, sr_, si = compress(sre, sim)
    return 0.7 * torch.mean((ym - sm) ** 2) + 0.3 * torch.mean((yr - sr_) ** 2 + (yi - si) ** 2)


def validation_set(clean, noise, n: int, seed: int = 1234):
    rng = random.Random(seed)
    cfg = MixConfig(seconds=3.0, p_clean_only=0.0, p_noise_only=0.0, snr_db=(-5.0, 15.0))
    return [make_mix(clean, noise, cfg, rng) for _ in range(n)]


@torch.no_grad()
def val_loss(net, vset, device):
    net.eval()
    tot = 0.0
    for x, s in vset:
        xt, st = torch.from_numpy(x)[None].to(device), torch.from_numpy(s)[None].to(device)
        _, yre, yim = net(xt)
        tot += float(spectral_loss(net, yre, yim, st))
    net.train()
    return tot / len(vset)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", nargs="*", default=[], help="folders with clean speech")
    ap.add_argument("--noise", nargs="*", default=[], help="folders with noise (incl. user contributions)")
    ap.add_argument("--synthetic", action="store_true", help="use generated signals (smoke test)")
    ap.add_argument("--out", default="runs/latest")
    ap.add_argument("--minutes", type=float, default=60.0, help="training time budget")
    ap.add_argument("--max-steps", type=int, default=0)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--seconds", type=float, default=2.0, help="length of each training mixture")
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--hidden", type=int, default=128)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--val-every", type=int, default=200)
    ap.add_argument("--val-n", type=int, default=24)
    ap.add_argument("--init", help="checkpoint to fine-tune from")
    ap.add_argument("--version", default=time.strftime("%Y.%m.%d"))
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)

    torch.manual_seed(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tc, tn, vc, vn = build_sources(a.clean, a.noise, a.synthetic, seed=a.seed)
    if not a.synthetic:
        print(f"clean files: {len(tc)} train / {len(vc)} val   noise files: {len(tn)} train / {len(vn)} val")

    net = NFNet(hidden=a.hidden).to(device)
    if a.init:
        net.load_state_dict(torch.load(a.init, map_location=device)["model"])
    print(f"NFNet: {count_params(net):,} params, ~{macs_per_frame(net) / 1e6:.1f} M MACs / 10 ms frame, device={device}")
    opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=1e-4)

    loader = DataLoader(MixStream(tc, tn, MixConfig(seconds=a.seconds), a.seed), batch_size=a.batch,
                        num_workers=a.workers, persistent_workers=a.workers > 0)
    vset = validation_set(vc, vn, a.val_n)
    best, step, t0 = float("inf"), 0, time.time()
    budget = a.minutes * 60
    history = []
    for x, s in loader:
        x, s = x.to(device), s.to(device)
        frac = min(1.0, (time.time() - t0) / budget)
        if a.max_steps:
            frac = max(frac, step / a.max_steps)
        for g in opt.param_groups:   # cosine decay over the time budget, short warm-up
            g["lr"] = a.lr * min(1.0, (step + 1) / 200) * (0.05 + 0.95 * 0.5 * (1 + np.cos(np.pi * frac)))
        _, yre, yim = net(x)
        loss = spectral_loss(net, yre, yim, s)
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 3.0)
        opt.step()
        step += 1
        done = frac >= 1.0 or (a.max_steps and step >= a.max_steps)
        if step % a.val_every == 0 or done:
            v = val_loss(net, vset, device)
            history.append({"step": step, "minutes": round((time.time() - t0) / 60, 2), "train": float(loss), "val": v})
            mark = ""
            if v < best:
                best = v
                torch.save({"model": net.state_dict(), "hidden": a.hidden, "step": step, "val": v}, out / "best.pt")
                mark = " *"
            print(f"step {step:6d}  {history[-1]['minutes']:6.1f} min  train {float(loss):.4f}  val {v:.4f}{mark}", flush=True)
        if done:
            break

    ckpt = torch.load(out / "best.pt", map_location="cpu")
    net = NFNet(hidden=a.hidden)
    net.load_state_dict(ckpt["model"])
    net.eval()

    from .export import export_onnx
    from .evaluate import evaluate
    onnx_path = out / "model.onnx"
    export_onnx(net, onnx_path)
    eval_set = validation_set(vc, vn, a.val_n, seed=999)
    metrics = evaluate(str(onnx_path), eval_set)
    from noise_filter.model_update import bundled_model
    cur = bundled_model()
    if cur:   # score the model that ships today on the same mixtures, for the publish gate
        metrics["current"] = evaluate(str(cur["path"]), eval_set)["nfnet"]
        metrics["current"]["version"] = cur["version"]
    meta = {
        "name": "nfnet", "version": a.version, "sample_rate": 48000, "frame": 480,
        "params": count_params(net), "macs_per_frame": macs_per_frame(net), "hidden": a.hidden,
        "steps": ckpt["step"], "val_loss": ckpt["val"], "train_minutes": round((time.time() - t0) / 60, 1),
        "data": "synthetic" if a.synthetic else {"clean": a.clean, "noise": a.noise},
        "metrics": metrics, "history": history,
    }
    from .export import sha256
    meta["sha256"] = sha256(onnx_path)
    (out / "model.json").write_text(json.dumps(meta, indent=2))
    (out / "report.md").write_text(report_md(meta))
    print(report_md(meta))


def report_md(meta) -> str:
    m = meta["metrics"]
    rows = ["| | SI-SDR (dB) | STOI | PESQ-WB | noise left on noise-only parts (dB) |", "|---|---|---|---|---|"]
    labels = [("noisy", "Noisy input"), ("spectral", "Spectral DSP"), ("nfnet", f"NFNet {meta['version']} (new)")]
    if "current" in m:
        labels.insert(2, ("current", f"NFNet {m['current'].get('version')} (shipped now)"))
    for k, label in labels:
        r = m[k]
        pesq = f"{r['pesq']:.2f}" if r.get("pesq") is not None else "n/a"
        rows.append(f"| {label} | {r['si_sdr']:.2f} | {r['stoi']:.3f} | {pesq} | {r['residual_db']:.1f} |")
    return (f"# NFNet {meta['version']}\n\n{meta['params']:,} parameters, "
            f"{meta['macs_per_frame'] / 1e6:.1f} M MACs per 10 ms frame, "
            f"{m['nfnet']['ms_per_frame']:.3f} ms per frame on this CPU (ONNX Runtime, 1 thread)\n\n"
            + "\n".join(rows) + "\n")


if __name__ == "__main__":
    main()
