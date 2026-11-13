"""Parametric equalizer: up to 8 bands of biquad (IIR) filters.

Band types: peak, low/high shelf, low/high-pass (Butterworth, 12-48 dB/octave),
band-pass and notch. Coefficients follow the RBJ "Audio EQ Cookbook" and are computed
in float64 exactly like the C++ port (cpp/src/eq.cpp), so both produce the same audio.

A band is a plain dict (it is stored as-is in config.json):
    {"type": "peak", "freq": 1000.0, "gain": 0.0, "q": 0.71, "slope": 12, "on": True}
"""
from __future__ import annotations

import math

import numpy as np

from .constants import SAMPLE_RATE

TYPES = ["peak", "lowshelf", "highshelf", "lowpass", "highpass", "bandpass", "notch"]
TYPE_ID = {t: i for i, t in enumerate(TYPES)}
SLOPES = [12, 24, 36, 48]
MAX_BANDS = 8
MAX_SECTIONS_PER_BAND = 4
GAIN_TYPES = {"peak", "lowshelf", "highshelf"}      # bands whose gain matters
SLOPE_TYPES = {"lowpass", "highpass"}               # bands with a selectable slope
FREQ_MIN, FREQ_MAX = 20.0, 20000.0
GAIN_MIN, GAIN_MAX = -24.0, 24.0
Q_MIN, Q_MAX = 0.1, 18.0

try:                                   # vectorized biquads when SciPy is around (dev installs)
    from scipy.signal import sosfilt as _sosfilt
except Exception:                      # the frozen app uses the C++ core instead
    _sosfilt = None


def band(type: str = "peak", freq: float = 1000.0, gain: float = 0.0, q: float = 0.71,
         slope: int = 12, on: bool = True) -> dict:
    return normalize({"type": type, "freq": freq, "gain": gain, "q": q, "slope": slope, "on": on})


def normalize(b: dict) -> dict:
    """Clamp a band read from the UI or config.json into valid ranges."""
    t = b.get("type", "peak")
    t = t if t in TYPE_ID else "peak"
    slope = int(b.get("slope", 12))
    slope = min(SLOPES, key=lambda s: abs(s - slope))
    return {"type": t,
            "freq": float(min(FREQ_MAX, max(FREQ_MIN, float(b.get("freq", 1000.0))))),
            "gain": float(min(GAIN_MAX, max(GAIN_MIN, float(b.get("gain", 0.0))))),
            "q": float(min(Q_MAX, max(Q_MIN, float(b.get("q", 0.71))))),
            "slope": slope,
            "on": bool(b.get("on", True))}


def butterworth_qs(order: int) -> list[float]:
    """Q of each 2nd-order section of an even-order Butterworth filter."""
    return [1.0 / (2.0 * math.cos(math.pi * (2 * k + 1) / (2 * order))) for k in range(order // 2)]


def design(b: dict, fs: int = SAMPLE_RATE) -> list[tuple[float, float, float, float, float]]:
    """Normalized sections (b0, b1, b2, a1, a2) for one band; [] when it is off."""
    b = normalize(b)
    if not b["on"]:
        return []
    t = b["type"]
    f0 = min(b["freq"], 0.45 * fs)
    w0 = 2.0 * math.pi * f0 / fs
    cosw, sinw = math.cos(w0), math.sin(w0)

    def section(q: float):
        alpha = sinw / (2.0 * q)
        A = 10.0 ** (b["gain"] / 40.0)
        if t == "peak":
            c = (1 + alpha * A, -2 * cosw, 1 - alpha * A, 1 + alpha / A, -2 * cosw, 1 - alpha / A)
        elif t == "lowshelf":
            sa = 2.0 * math.sqrt(A) * alpha
            c = (A * ((A + 1) - (A - 1) * cosw + sa), 2 * A * ((A - 1) - (A + 1) * cosw),
                 A * ((A + 1) - (A - 1) * cosw - sa),
                 (A + 1) + (A - 1) * cosw + sa, -2 * ((A - 1) + (A + 1) * cosw), (A + 1) + (A - 1) * cosw - sa)
        elif t == "highshelf":
            sa = 2.0 * math.sqrt(A) * alpha
            c = (A * ((A + 1) + (A - 1) * cosw + sa), -2 * A * ((A - 1) + (A + 1) * cosw),
                 A * ((A + 1) + (A - 1) * cosw - sa),
                 (A + 1) - (A - 1) * cosw + sa, 2 * ((A - 1) - (A + 1) * cosw), (A + 1) - (A - 1) * cosw - sa)
        elif t == "lowpass":
            c = ((1 - cosw) / 2, 1 - cosw, (1 - cosw) / 2, 1 + alpha, -2 * cosw, 1 - alpha)
        elif t == "highpass":
            c = ((1 + cosw) / 2, -(1 + cosw), (1 + cosw) / 2, 1 + alpha, -2 * cosw, 1 - alpha)
        elif t == "bandpass":   # constant 0 dB peak gain
            c = (alpha, 0.0, -alpha, 1 + alpha, -2 * cosw, 1 - alpha)
        else:                   # notch
            c = (1.0, -2 * cosw, 1.0, 1 + alpha, -2 * cosw, 1 - alpha)
        a0 = c[3]
        return (c[0] / a0, c[1] / a0, c[2] / a0, c[4] / a0, c[5] / a0)

    if t in SLOPE_TYPES:
        order = b["slope"] // 6
        # 12 dB/oct keeps the user's Q (resonance); steeper slopes are pure Butterworth.
        qs = [b["q"]] if order == 2 else butterworth_qs(order)
        return [section(q) for q in qs]
    return [section(b["q"])]


def response_db(bands: list[dict], freqs: np.ndarray, fs: int = SAMPLE_RATE) -> np.ndarray:
    """Magnitude response in dB of the given bands at freqs (Hz): drawn as the EQ curve."""
    z = np.exp(-1j * 2 * np.pi * np.asarray(freqs, np.float64) / fs)
    h = np.ones_like(z)
    for b in bands:
        for b0, b1, b2, a1, a2 in design(b, fs):
            h *= (b0 + b1 * z + b2 * z * z) / (1 + a1 * z + a2 * z * z)
    return 20 * np.log10(np.maximum(np.abs(h), 1e-9))


class Equalizer:
    """Stateful EQ for 10 ms frames. set() keeps filter states of bands whose section
    count did not change, so dragging a band does not click."""

    def __init__(self, enabled: bool = False, bands: list[dict] | None = None):
        self.enabled = False
        self.bands: list[dict] = []
        self._sos = np.zeros((0, 6))
        self._z = np.zeros((0, 2))
        self._layout: list[int] = []
        self.set(enabled, bands or [])

    def set(self, enabled: bool, bands: list[dict]) -> None:
        self.enabled = bool(enabled)
        self.bands = [normalize(b) for b in bands[:MAX_BANDS]]
        secs, layout = [], []
        for b in self.bands:
            s = design(b)
            layout.append(len(s))
            secs += s
        old_z, old_layout = self._z, self._layout
        z = np.zeros((len(secs), 2))
        i = j = 0
        for k, n in enumerate(layout):          # carry states band by band when the shape matches
            if k < len(old_layout) and old_layout[k] == n:
                z[i:i + n] = old_z[j:j + n]
            i += n
            j += old_layout[k] if k < len(old_layout) else 0
        self._sos = np.array([[b0, b1, b2, 1.0, a1, a2] for b0, b1, b2, a1, a2 in secs]).reshape(-1, 6)
        self._z, self._layout = z, layout

    @property
    def active(self) -> bool:
        return self.enabled and len(self._sos) > 0

    def process(self, x: np.ndarray) -> np.ndarray:
        if not self.active:
            return x
        if _sosfilt is not None:
            y, self._z = _sosfilt(self._sos, x.astype(np.float64), zi=self._z)
            return y.astype(np.float32)
        y = x.astype(np.float64)
        for s, z in zip(self._sos, self._z):    # direct form II transposed, as in C++
            b0, b1, b2, _, a1, a2 = s
            z0, z1 = z
            out = np.empty_like(y)
            for i, v in enumerate(y):
                o = b0 * v + z0
                z0 = b1 * v - a1 * o + z1
                z1 = b2 * v - a2 * o
                out[i] = o
            z[0], z[1] = z0, z1
            y = out
        return y.astype(np.float32)


PRESETS: dict[str, list[dict]] = {
    "flat": [],
    "voice_clarity": [band("highpass", 90, slope=24), band("peak", 250, -3, 1.0),
                      band("peak", 3000, 3, 0.9), band("highshelf", 8000, 2, 0.7)],
    "hum_50": [band("notch", 50, q=8), band("notch", 100, q=8), band("notch", 150, q=8)],
    "hum_60": [band("notch", 60, q=8), band("notch", 120, q=8), band("notch", 180, q=8)],
    "telephone": [band("highpass", 300, slope=24), band("lowpass", 3400, slope=24), band("peak", 1500, 3, 1.0)],
    "podcast": [band("highpass", 80, slope=12), band("lowshelf", 150, 2, 0.7), band("peak", 400, -2, 1.2),
                band("peak", 4500, 2.5, 1.0), band("highshelf", 10000, 1.5, 0.7)],
    "reduce_boom": [band("highpass", 120, slope=36), band("peak", 200, -4, 1.0)],
    "reduce_hiss": [band("lowpass", 9000, slope=24), band("highshelf", 6000, -4, 0.7)],
}
