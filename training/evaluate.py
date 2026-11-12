"""Compare noisy input, the spectral DSP denoiser and an ONNX model on the same mixtures.

Both processors run through the app's real Pipeline (frame by frame, gate off, high-pass on),
so the numbers reflect what users hear. Outputs are delayed by one 10 ms frame and are
re-aligned before scoring.
"""
from __future__ import annotations

import time

import numpy as np

from noise_filter.core import FRAME_SIZE, Pipeline, PipelineConfig

SR = 48_000


def si_sdr(est, ref):
    ref = ref - ref.mean()
    est = est - est.mean()
    a = np.dot(est, ref) / (np.dot(ref, ref) + 1e-12)
    t = a * ref
    return 10 * np.log10(np.sum(t ** 2) / (np.sum((est - t) ** 2) + 1e-12) + 1e-12)


def run_pipeline(cfg: PipelineConfig, x: np.ndarray):
    p = Pipeline(cfg)
    n = len(x) // FRAME_SIZE
    t0 = time.perf_counter()
    y = np.concatenate([p.process(x[i * FRAME_SIZE:(i + 1) * FRAME_SIZE]) for i in range(n)])
    ms = (time.perf_counter() - t0) / n * 1000
    y = np.concatenate([y[FRAME_SIZE:], np.zeros(FRAME_SIZE, np.float32)])  # undo 1-frame delay
    return y, ms


def scores(est, clean, noisy):
    from pystoi import stoi
    from scipy.signal import resample_poly
    r = {"si_sdr": si_sdr(est, clean), "stoi": float(stoi(clean, est, SR, extended=False))}
    try:
        from pesq import pesq
        r["pesq"] = float(pesq(16000, resample_poly(clean, 1, 3), resample_poly(est, 1, 3), "wb"))
    except Exception:
        r["pesq"] = None
    return r


def evaluate(onnx_path: str, vset) -> dict:
    base = dict(gate_enabled=False, highpass_hz=80.0)
    methods = {
        "noisy": None,
        "spectral": PipelineConfig(denoise="spectral", **base),
        "nfnet": PipelineConfig(denoise="onnx", onnx_model=onnx_path, **base),
    }
    acc = {k: {"si_sdr": [], "stoi": [], "pesq": [], "residual_db": [], "ms": []} for k in methods}
    for x, s in vset:
        n = len(x) // FRAME_SIZE * FRAME_SIZE
        x, s = x[:n], s[:n]
        for k, cfg in methods.items():
            if cfg is None:
                y, ms = x, 0.0
            else:
                y, ms = run_pipeline(cfg, x)
            # compare on the part after the first second (lets the DSP noise tracker adapt)
            sl = slice(SR, n - FRAME_SIZE)
            r = scores(y[sl], s[sl], x[sl])
            for m in ("si_sdr", "stoi", "pesq"):
                if r[m] is not None:
                    acc[k][m].append(r[m])
            quiet = np.abs(s[sl]) < 1e-4 * max(np.max(np.abs(s)), 1e-6)  # speech pauses
            noise_in = x[sl][quiet] if quiet.any() else x[sl]
            noise_out = y[sl][quiet] if quiet.any() else y[sl]
            acc[k]["residual_db"].append(20 * np.log10((np.std(noise_out) + 1e-9) / (np.std(noise_in) + 1e-9)))
            acc[k]["ms"].append(ms)
    out = {}
    for k, d in acc.items():
        out[k] = {m: (float(np.mean(v)) if v else None) for m, v in d.items() if m != "ms"}
        out[k]["ms_per_frame"] = float(np.mean(d["ms"]))
    return out
