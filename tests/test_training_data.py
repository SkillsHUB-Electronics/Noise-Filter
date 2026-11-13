"""Training mixtures must never be secretly clean because a noise clip was silent padding."""
import random

import numpy as np

from training.data import MixConfig, active_fraction, make_mix


class PaddedNoise:
    """Like an ESC-50 clip: a short sound followed by digital silence."""
    def segment(self, n, rng):
        x = np.zeros(n, np.float32)
        if rng.random() < 0.3:
            x[:] = np.random.default_rng(rng.randrange(1 << 30)).standard_normal(n) * 0.1
        return x


class Tone:
    def segment(self, n, rng):
        return (0.2 * np.sin(np.arange(n) * 0.05)).astype(np.float32)


def test_active_fraction():
    x = np.zeros(4800, np.float32)
    assert active_fraction(x) == 0.0
    x[:2400] = 0.1
    assert abs(active_fraction(x) - 0.5) < 1e-9


def test_mixes_skip_silent_noise():
    rng = random.Random(0)
    cfg = MixConfig(seconds=1.0, p_clean_only=0.0, p_noise_only=0.0)
    for _ in range(30):
        x, s = make_mix(Tone(), PaddedNoise(), cfg, rng)
        assert np.std(x - s) > 1e-4
