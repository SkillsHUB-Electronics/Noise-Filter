"""NFNet: small realtime speech denoiser (about 0.2 M parameters).

Same framing as the spectral denoiser in noise_filter/core: 480-sample hop (10 ms @ 48 kHz),
960-sample periodic sqrt-Hann window, 50 % overlap-add, so the algorithmic latency is one
frame. Per frame:

    |X|^2 per bin -> 32 ERB-like band energies -> log -> GRU x2 -> 32 band gains (sigmoid)
    -> per-bin gains -> X * gain -> inverse DFT -> window -> overlap-add

The DFT is done with fixed matrices instead of an STFT op so the exported ONNX graph only
uses MatMul / GRU / elementwise ops, which ONNX Runtime runs fast on any CPU (desktop and phone).

Streaming ONNX contract (see noise_filter/core/denoiser_onnx.py):
    inputs  frame [1,480], state_prev [1,480], state_tail [1,480], state_h [L,1,H]
    outputs frame_out [1,480], state_prev_out, state_tail_out, state_h_out   (same order)
"""
from __future__ import annotations

import math

import numpy as np
import torch
from torch import nn

SAMPLE_RATE = 48_000
HOP = 480
WIN = 2 * HOP
BINS = HOP + 1


def erb_bands(n_bands: int = 32, bins: int = BINS, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Triangular filterbank on the ERB scale, shape [bins, n_bands]; rows sum to 1."""
    freqs = np.linspace(0, sr / 2, bins)
    erb = lambda f: 21.4 * np.log10(1 + 0.00437 * f)
    inv = lambda e: (10 ** (e / 21.4) - 1) / 0.00437
    edges = inv(np.linspace(erb(0), erb(sr / 2), n_bands + 2))
    # keep the lowest bands at least 2 bins wide so every band sees energy
    min_w = 2 * (sr / 2) / (bins - 1)
    for i in range(1, len(edges)):
        edges[i] = max(edges[i], edges[i - 1] + min_w)
    edges = edges / edges[-1] * (sr / 2)
    fb = np.zeros((bins, n_bands), np.float32)
    for b in range(n_bands):
        lo, c, hi = edges[b], edges[b + 1], edges[b + 2]
        up = (freqs - lo) / max(c - lo, 1e-9)
        down = (hi - freqs) / max(hi - c, 1e-9)
        if b == 0:
            up = np.ones_like(up)            # flat down to DC
        if b == n_bands - 1:
            down = np.ones_like(down)        # flat up to Nyquist
        fb[:, b] = np.clip(np.minimum(up, down), 0, 1)
    fb /= fb.sum(1, keepdims=True) + 1e-9
    return fb


class NFNet(nn.Module):
    def __init__(self, n_bands: int = 32, hidden: int = 128, layers: int = 2, min_gain: float = 0.03):
        super().__init__()
        self.n_bands, self.hidden, self.layers, self.min_gain = n_bands, hidden, layers, min_gain
        n = np.arange(WIN)
        k = np.arange(BINS)
        win = np.sqrt(0.5 - 0.5 * np.cos(2 * np.pi * n / WIN)).astype(np.float32)
        ang = 2 * np.pi * np.outer(n, k) / WIN
        # forward real DFT: X = x @ (cos - j sin)
        self.register_buffer("window", torch.from_numpy(win))
        self.register_buffer("dft_re", torch.from_numpy(np.cos(ang).astype(np.float32)))
        self.register_buffer("dft_im", torch.from_numpy((-np.sin(ang)).astype(np.float32)))
        # inverse real DFT (numpy irfft convention): x = Re @ A + Im @ B
        w = np.full(BINS, 2.0)
        w[0] = w[-1] = 1.0
        self.register_buffer("idft_re", torch.from_numpy((w[:, None] * np.cos(ang.T) / WIN).astype(np.float32)))
        self.register_buffer("idft_im", torch.from_numpy((-w[:, None] * np.sin(ang.T) / WIN).astype(np.float32)))
        fb = erb_bands(n_bands)
        self.register_buffer("to_bands", torch.from_numpy(fb / (fb.sum(0, keepdims=True) + 1e-9)))  # band mean
        interp = fb.T / (fb.T.sum(0, keepdims=True) + 1e-9)  # [bands, bins], columns sum to 1
        self.register_buffer("to_bins", torch.from_numpy(interp.astype(np.float32)))

        self.inp = nn.Sequential(nn.Linear(n_bands, hidden), nn.Tanh())
        self.gru = nn.GRU(hidden, hidden, num_layers=layers, batch_first=True)
        self.out = nn.Linear(hidden, n_bands)
        nn.init.constant_(self.out.bias, 2.0)  # start close to pass-through

    # ---------------------------------------------------------------- shared math
    def _features(self, re, im):
        p = re * re + im * im                                   # [..., BINS]
        band = p @ self.to_bands                                # [..., bands]
        return torch.log10(band + 1e-10) / 4.0 + 1.5            # roughly in [-1, 1] for speech levels

    def _gains(self, h):
        g = torch.sigmoid(self.out(h))                          # band gains in (0,1)
        g = self.min_gain + (1 - self.min_gain) * g
        return g @ self.to_bins                                 # per-bin gains

    # ---------------------------------------------------------------- training (whole sequences)
    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """x: [B, N] waveform (N multiple of HOP). Returns (enhanced waveform [B, N], spec_re, spec_im)
        where the spectra are the enhanced STFT frames [B, T, BINS] used by the loss."""
        B, N = x.shape
        pad = torch.cat([x.new_zeros(B, HOP), x], 1)            # frame t = [x_{t-1}, x_t] like streaming
        frames = pad.unfold(1, WIN, HOP) * self.window          # [B, T, WIN]
        re, im = frames @ self.dft_re, frames @ self.dft_im
        h, _ = self.gru(self.inp(self._features(re, im)))
        g = self._gains(h)
        yre, yim = re * g, im * g
        y = (yre @ self.idft_re + yim @ self.idft_im) * self.window  # [B, T, WIN]
        out = y[:, :, :HOP].clone()
        out[:, 1:] += y[:, :-1, HOP:]                           # overlap-add
        return out.reshape(B, -1), yre, yim

    def stft(self, x: torch.Tensor):
        B = x.shape[0]
        pad = torch.cat([x.new_zeros(B, HOP), x], 1)
        frames = pad.unfold(1, WIN, HOP) * self.window
        return frames @ self.dft_re, frames @ self.dft_im

    # ---------------------------------------------------------------- streaming (ONNX export)
    def step(self, frame, state_prev, state_tail, state_h):
        buf = torch.cat([state_prev, frame], 1) * self.window  # [1, WIN]
        re, im = buf @ self.dft_re, buf @ self.dft_im
        z = self.inp(self._features(re, im)).unsqueeze(1)      # [1, 1, H]
        h, state_h_out = self.gru(z, state_h)
        g = self._gains(h[:, 0])
        y = ((re * g) @ self.idft_re + (im * g) @ self.idft_im) * self.window
        frame_out = state_tail + y[:, :HOP]
        return frame_out, frame, y[:, HOP:], state_h_out

    def init_state(self):
        return (torch.zeros(1, HOP), torch.zeros(1, HOP), torch.zeros(self.layers, 1, self.hidden))


class StepWrapper(nn.Module):
    """nn.Module whose forward() is the streaming step, for torch.onnx.export."""

    def __init__(self, net: NFNet):
        super().__init__()
        self.net = net

    def forward(self, frame, state_prev, state_tail, state_h):
        return self.net.step(frame, state_prev, state_tail, state_h)


def count_params(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters())


def macs_per_frame(m: NFNet) -> int:
    h, b, L = m.hidden, m.n_bands, m.layers
    dft = 2 * WIN * BINS * 2                 # forward + inverse
    bands = BINS * b * 2
    gru = L * 3 * (h * h * 2)
    return dft + bands + gru + b * h * 2


if __name__ == "__main__":
    net = NFNet()
    print(f"params {count_params(net):,}  ~{macs_per_frame(net) / 1e6:.2f} M MACs per 10 ms frame")
    x = torch.randn(2, HOP * 50) * 0.1
    y, _, _ = net(x)
    print(y.shape, math.isfinite(float(y.abs().sum())))
