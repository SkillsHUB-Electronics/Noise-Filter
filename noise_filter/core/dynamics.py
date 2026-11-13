"""Compressor and limiter (zero latency), ported 1:1 to C++ in cpp/src/dynamics.cpp.

Compressor: feed-forward, soft knee, gain computed per sample in the log domain and
smoothed with separate attack/release (Giannoulis, Massberg & Reiss, JAES 2012).
Limiter: per-sample peak limiter with instant attack and smooth release, so the output
never exceeds the ceiling and no look-ahead delay is added.
"""
from __future__ import annotations

import math

import numpy as np

from .constants import SAMPLE_RATE

KNEE_DB = 6.0
LIMITER_RELEASE_MS = 60.0


def _coef(ms: float) -> float:
    return math.exp(-1.0 / (max(ms, 0.01) * 1e-3 * SAMPLE_RATE))


def static_curve_db(x_db, threshold_db: float, ratio: float, knee_db: float = KNEE_DB):
    """Output level for an input level (dB), the compressor's transfer curve."""
    x = np.asarray(x_db, np.float64)
    d = x - threshold_db
    y = np.where(2 * d < -knee_db, x,
                 np.where(2 * np.abs(d) <= knee_db,
                          x + (1 / ratio - 1) * (d + knee_db / 2) ** 2 / (2 * knee_db),
                          threshold_db + d / ratio))
    return y


class Compressor:
    def __init__(self, threshold_db=-24.0, ratio=3.0, attack_ms=10.0, release_ms=150.0, makeup_db=0.0):
        self.gs = 0.0          # smoothed gain change, dB (<= 0)
        self.set(threshold_db, ratio, attack_ms, release_ms, makeup_db)

    def set(self, threshold_db, ratio, attack_ms, release_ms, makeup_db):
        self.threshold_db, self.ratio = float(threshold_db), max(1.0, float(ratio))
        self.attack_ms, self.release_ms, self.makeup_db = float(attack_ms), float(release_ms), float(makeup_db)
        self._aa, self._ar = _coef(self.attack_ms), _coef(self.release_ms)

    @property
    def gr_db(self) -> float:
        """Current gain reduction in dB (>= 0), for the meter."""
        return -self.gs

    def process(self, x: np.ndarray) -> np.ndarray:
        xd = x.astype(np.float64)
        level = 20.0 * np.log10(np.maximum(np.abs(xd), 1e-9))
        gc = static_curve_db(level, self.threshold_db, self.ratio) - level
        aa, ar, gs = self._aa, self._ar, self.gs
        g = np.empty_like(gc)
        for i, c in enumerate(gc):        # attack while reducing more, release while recovering
            gs = aa * gs + (1 - aa) * c if c < gs else ar * gs + (1 - ar) * c
            g[i] = gs
        self.gs = gs
        return (xd * 10.0 ** ((g + self.makeup_db) / 20.0)).astype(np.float32)


class Limiter:
    def __init__(self, ceiling_db=-1.0, release_ms=LIMITER_RELEASE_MS):
        self.g = 1.0
        self._ar = _coef(release_ms)
        self.set(ceiling_db)

    def set(self, ceiling_db):
        self.ceiling_db = float(ceiling_db)
        self.ceiling = 10.0 ** (self.ceiling_db / 20.0)

    @property
    def gr_db(self) -> float:
        return -20.0 * math.log10(max(self.g, 1e-9))

    def process(self, x: np.ndarray) -> np.ndarray:
        xd = x.astype(np.float64)
        target = np.minimum(1.0, self.ceiling / np.maximum(np.abs(xd), 1e-9))
        ar, g = self._ar, self.g
        out = np.empty_like(xd)
        for i, t in enumerate(target):
            g = t if t < g else ar * g + (1 - ar) * t
            g = min(g, t)                 # never above what this sample allows
            out[i] = xd[i] * g
        self.g = g
        return out.astype(np.float32)
