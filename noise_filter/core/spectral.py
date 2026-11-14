import numpy as np
from .constants import FRAME_SIZE, SAMPLE_RATE

# Vocal / singing mode: keep harmonics, breath and the natural decay of sung notes.
VOCAL_FLOOR = 0.12        # residual floor ~ -18 dB instead of -22 dB: less "dry" sound
VOCAL_RISE = 0.002        # adaptive noise estimate climbs slower, so held notes are not learned as noise
VOCAL_ATTACK = 0.6        # gain smoothing: open like the standard mode ...
VOCAL_RELEASE = 0.75      # ... close slowly, keeping note tails and room ambience
VOCAL_PEAK_SNR = 3.0      # spectral peak at least ~5 dB above the noise estimate = harmonic
VOCAL_PEAK_GAIN = 1.0     # gain floor for a harmonic peak bin
VOCAL_SIDE_GAIN = 0.6     # gain floor for its neighbours (window main lobe)
VOCAL_HF_START, VOCAL_HF_SPAN, VOCAL_HF_EASE = 3000.0, 6000.0, 0.15   # strength eases off above 3 kHz


class SpectralDenoiser:
    """Streaming spectral-subtraction denoiser (classic DSP baseline).

    50% overlap STFT, sqrt-Hann window: algorithmic latency = 1 frame (10 ms).
    Noise estimate is either a learned profile (see learn_profile) or adaptive
    (fast-falling / slow-rising minimum tracker).

    vocal=True keeps the harmonics of speech and singing: spectral peaks that stand
    out from the noise (and their neighbours) get a high gain floor, the noise tracker
    does not climb into them, the overall floor is higher, high frequencies are cut
    more gently and gains close slowly. Ported 1:1 to cpp/src/dsp.cpp.
    """

    def __init__(self, strength: float = 1.0, floor: float = 0.08,
                 smoothing: float = 0.6, rise: float = 0.003, vocal: bool = False):
        n = FRAME_SIZE
        self.n = n
        self.win = np.sqrt(np.hanning(2 * n + 1)[:-1]).astype(np.float32)  # periodic
        self.strength, self.floor, self.smoothing, self.rise = strength, floor, smoothing, rise
        self.vocal = vocal
        self.prev = np.zeros(n, np.float32)
        self.tail = np.zeros(n, np.float32)
        self.ps = None
        self.pv = None               # fast-smoothed power, for the harmonic peak test (vocal mode)
        self.noise = None            # noise power spectrum (n+1 bins)
        self.profile = None          # fixed learned profile, overrides adaptive
        self.gain_prev = np.ones(n + 1, np.float32)
        f = np.arange(n + 1) * SAMPLE_RATE / (2 * n)
        self.hf_weight = (1.0 - VOCAL_HF_EASE * np.clip((f - VOCAL_HF_START) / VOCAL_HF_SPAN, 0, 1)).astype(np.float32)
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

    @staticmethod
    def harmonic_floor(pv: np.ndarray, noise: np.ndarray) -> np.ndarray:
        """Gain floor per bin: VOCAL_PEAK_GAIN on spectral peaks well above the noise,
        VOCAL_SIDE_GAIN on their direct neighbours, 0 elsewhere."""
        k = np.arange(1, len(pv) - 1)
        peak = np.zeros(len(pv), bool)
        peak[k] = (pv[k] > pv[k - 1]) & (pv[k] >= pv[k + 1]) & (pv[k] > VOCAL_PEAK_SNR * noise[k])
        side = np.zeros_like(peak)
        side[:-1] |= peak[1:]
        side[1:] |= peak[:-1]
        return np.where(peak, np.float32(VOCAL_PEAK_GAIN),
                        np.where(side, np.float32(VOCAL_SIDE_GAIN), np.float32(0))).astype(np.float32)

    def process(self, x: np.ndarray) -> np.ndarray:
        buf = np.concatenate([self.prev, x]).astype(np.float32)
        self.prev = x.copy()
        spec = np.fft.rfft(buf * self.win)
        p = (spec.real ** 2 + spec.imag ** 2).astype(np.float32)

        if self._learn is not None:
            self._learn.append(p)

        vocal = self.vocal
        if vocal:
            self.pv = p.copy() if self.pv is None else (0.5 * self.pv + 0.5 * p).astype(np.float32)

        if self.profile is not None:
            noise = self.profile
            hfloor = self.harmonic_floor(self.pv, noise) if vocal else None
        else:
            if self.noise is None:
                self.ps, self.noise = p.copy(), p.copy()
            self.ps = 0.9 * self.ps + 0.1 * p            # smooth first: raw bin power is very noisy
            if vocal:
                hfloor = self.harmonic_floor(self.pv, self.noise * 2.0)
                up = np.where(hfloor > 0, np.float32(1.0), np.float32(1.0 + min(self.rise, VOCAL_RISE)))
                self.noise = np.minimum(self.ps, self.noise * up)   # never climbs into a harmonic
            else:
                hfloor = None
                self.noise = np.minimum(self.ps, self.noise * (1.0 + self.rise))
            noise = self.noise * 2.0   # bias: min-tracker underestimates the mean

        if vocal:
            gain = 1.0 - self.strength * self.hf_weight * noise / (p + 1e-12)
            gain = np.maximum(np.maximum(gain, max(self.floor, VOCAL_FLOOR)), hfloor)
            k = np.where(gain > self.gain_prev, np.float32(VOCAL_ATTACK), np.float32(VOCAL_RELEASE))
            gain = k * self.gain_prev + (1 - k) * gain
        else:
            gain = np.maximum(1.0 - self.strength * noise / (p + 1e-12), self.floor)
            gain = self.smoothing * self.gain_prev + (1 - self.smoothing) * gain
        self.gain_prev = gain.astype(np.float32)

        out = np.fft.irfft(spec * gain, 2 * self.n).astype(np.float32) * self.win
        y = self.tail + out[: self.n]
        self.tail = out[self.n:]
        return y
