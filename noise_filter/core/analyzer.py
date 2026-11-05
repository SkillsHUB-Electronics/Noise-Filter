import numpy as np
from .constants import SAMPLE_RATE


class SpectrumAnalyzer:
    """Rolling FFT magnitude (dBFS) of the last `size` samples. Used for input and output."""

    def __init__(self, size: int = 2048, smoothing: float = 0.7):
        self.size = size
        self.buf = np.zeros(size, np.float32)
        self.win = np.hanning(size).astype(np.float32)
        self.smoothing = smoothing
        self.db = np.full(size // 2 + 1, -120.0, np.float32)
        self.freqs = np.fft.rfftfreq(size, 1 / SAMPLE_RATE)

    def push(self, frame: np.ndarray) -> None:
        n = len(frame)
        self.buf = np.roll(self.buf, -n)
        self.buf[-n:] = frame

    def spectrum_db(self) -> np.ndarray:
        mag = np.abs(np.fft.rfft(self.buf * self.win)) / (self.size / 4)
        db = 20 * np.log10(mag + 1e-9)
        self.db = self.smoothing * self.db + (1 - self.smoothing) * db.astype(np.float32)
        return self.db

    def level_db(self) -> float:
        return float(20 * np.log10(np.sqrt(np.mean(self.buf[-480:] ** 2)) + 1e-9))
