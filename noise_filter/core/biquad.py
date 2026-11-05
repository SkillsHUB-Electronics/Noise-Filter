import math
import numpy as np


class HighPass:
    """2nd-order Butterworth high-pass (removes rumble / DC), stateful per frame."""

    def __init__(self, cutoff_hz: float = 80.0, sample_rate: int = 48_000):
        w0 = 2 * math.pi * cutoff_hz / sample_rate
        cosw, alpha = math.cos(w0), math.sin(w0) / (2 * math.sqrt(0.5))
        a0 = 1 + alpha
        self.b = np.array([(1 + cosw) / 2, -(1 + cosw), (1 + cosw) / 2]) / a0
        self.a = np.array([1.0, -2 * cosw / a0, (1 - alpha) / a0])
        self.z = np.zeros(2)

    def process(self, x: np.ndarray) -> np.ndarray:
        b, a, z = self.b, self.a, self.z
        y = np.empty_like(x)
        # Direct form II transposed; explicit loop mirrors the C++ port.
        for i, s in enumerate(x):
            o = b[0] * s + z[0]
            z[0] = b[1] * s - a[1] * o + z[1]
            z[1] = b[2] * s - a[2] * o
            y[i] = o
        return y
