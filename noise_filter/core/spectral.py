import numpy as np
from .constants import FRAME_SIZE


class SpectralDenoiser:
    """Streaming spectral-subtraction denoiser (classic DSP baseline).

    50% overlap STFT, sqrt-Hann window: algorithmic latency = 1 frame (10 ms).
    Noise estimate is either a learned profile (see learn_profile) or adaptive
    (fast-falling / slow-rising minimum tracker).
    """

    def __init__(self, strength: float = 1.0, floor: float = 0.08,
                 smoothing: float = 0.6, rise: float = 0.003):
        n = FRAME_SIZE
        self.n = n
        self.win = np.sqrt(np.hanning(2 * n + 1)[:-1]).astype(np.float32)  # periodic
        self.strength, self.floor, self.smoothing, self.rise = strength, floor, smoothing, rise
        self.prev = np.zeros(n, np.float32)
        self.tail = np.zeros(n, np.float32)
        self.ps = None
        self.noise = None            # noise power spectrum (n+1 bins)
        self.profile = None          # fixed learned profile, overrides adaptive
        self.gain_prev = np.ones(n + 1, np.float32)
        self._learn = None

    # ---- noise profile learning (record a few seconds of room noise) ----
    def start_learning(self):
        self._learn = []

    def finish_learning(self):
        if self._learn:
            self.profile = np.mean(self._learn, axis=0).astype(np.float32)
        self._learn = None

    def clear_profile(self):
        self.profile = None

    def process(self, x: np.ndarray) -> np.ndarray:
        buf = np.concatenate([self.prev, x]).astype(np.float32)
        self.prev = x.copy()
        spec = np.fft.rfft(buf * self.win)
        p = (spec.real ** 2 + spec.imag ** 2).astype(np.float32)

        if self._learn is not None:
            self._learn.append(p)

        if self.profile is not None:
            noise = self.profile
        else:
            if self.noise is None:
                self.ps, self.noise = p.copy(), p.copy()
            self.ps = 0.9 * self.ps + 0.1 * p            # smooth first: raw bin power is very noisy
            self.noise = np.minimum(self.ps, self.noise * (1.0 + self.rise))
            noise = self.noise * 2.0   # bias: min-tracker underestimates the mean

        gain = np.maximum(1.0 - self.strength * noise / (p + 1e-12), self.floor)
        gain = self.smoothing * self.gain_prev + (1 - self.smoothing) * gain
        self.gain_prev = gain.astype(np.float32)

        out = np.fft.irfft(spec * gain, 2 * self.n).astype(np.float32) * self.win
        y = self.tail + out[: self.n]
        self.tail = out[self.n:]
        return y
