import numpy as np

VOCAL_RELEASE = 0.02     # vocal mode: close ~2.5x slower, so soft note endings and breaths survive
VOCAL_FLOOR_DB = -25.0   # ... and only dip to -25 dB instead of -40 dB


class NoiseGate:
    """Simple RMS gate with attack/release smoothing, applied per frame."""

    def __init__(self, threshold_db=-55.0, attack=0.5, release=0.05, floor_db=-40.0):
        self.threshold = 10 ** (threshold_db / 20)
        self.floor = 10 ** (floor_db / 20)
        self.attack, self.release = attack, release
        self.gain = 1.0

    def set_shape(self, release: float, floor_db: float) -> None:
        self.release, self.floor = release, 10 ** (floor_db / 20)

    def process(self, x: np.ndarray) -> np.ndarray:
        rms = float(np.sqrt(np.mean(x * x) + 1e-12))
        target = 1.0 if rms >= self.threshold else self.floor
        k = self.attack if target > self.gain else self.release
        g0 = self.gain
        self.gain = g0 + k * (target - g0)
        return x * np.linspace(g0, self.gain, len(x), endpoint=False, dtype=np.float32)
