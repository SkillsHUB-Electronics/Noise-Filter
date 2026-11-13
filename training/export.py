"""Export NFNet as a streaming ONNX model and check it against PyTorch."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import torch

from .model import HOP, NFNet, StepWrapper


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def export_onnx(net: NFNet, path, check: bool = True) -> Path:
    net = net.eval().cpu()
    path = Path(path)
    args = (torch.zeros(1, HOP),) + net.init_state()
    torch.onnx.export(
        StepWrapper(net), args, str(path), opset_version=17, dynamo=False,
        input_names=["frame", "state_prev", "state_tail", "state_h"],
        output_names=["frame_out", "state_prev_out", "state_tail_out", "state_h_out"],
    )
    if check:
        check_onnx(net, path)
    return path


@torch.no_grad()
def check_onnx(net: NFNet, path, frames: int = 50) -> float:
    """Stream random audio through ONNX Runtime and the PyTorch batch model; they must agree."""
    import onnxruntime as ort
    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    x = (np.random.default_rng(0).standard_normal(HOP * frames) * 0.05).astype(np.float32)
    ref, _, _ = net(torch.from_numpy(x)[None])
    ref = ref[0].numpy()
    st = [s.numpy() for s in net.init_state()]
    out = []
    for t in range(frames):
        y, *st = sess.run(None, {"frame": x[None, t * HOP:(t + 1) * HOP], "state_prev": st[0],
                                 "state_tail": st[1], "state_h": st[2]})
        out.append(y[0])
    err = float(np.max(np.abs(np.concatenate(out) - ref)))
    if err > 1e-4:
        raise RuntimeError(f"ONNX streaming output differs from PyTorch by {err}")
    return err


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("checkpoint")
    ap.add_argument("out")
    a = ap.parse_args()
    ck = torch.load(a.checkpoint, map_location="cpu")
    net = NFNet(hidden=ck.get("hidden", 128))
    net.load_state_dict(ck["model"])
    export_onnx(net, a.out)
    print(f"wrote {a.out}  sha256 {sha256(a.out)}")
