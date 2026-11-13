import json, time
import numpy as np
from noise_filter.core import Pipeline, PipelineConfig, FRAME_SIZE, SAMPLE_RATE, FRAME_MS
from noise_filter.core.analyzer import SpectrumAnalyzer
from noise_filter.i18n import tr

rng = np.random.default_rng(0)


def run(pipe, x):
    n = len(x) // FRAME_SIZE
    return np.concatenate([pipe.process(x[i * FRAME_SIZE:(i + 1) * FRAME_SIZE]) for i in range(n)])


def tone(f, secs, amp=0.3):
    t = np.arange(int(SAMPLE_RATE * secs)) / SAMPLE_RATE
    return (amp * np.sin(2 * np.pi * f * t)).astype(np.float32)


def rms_db(x): return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12)


def test_bypass_is_identity():
    p = Pipeline(PipelineConfig(bypass=True))
    x = tone(440, 0.2)
    np.testing.assert_allclose(run(p, x), x[: len(run(p, x))], atol=1e-6)


def test_frame_size_enforced():
    import pytest
    with pytest.raises(AssertionError):
        Pipeline().process(np.zeros(100, np.float32))


def test_denoise_reduces_stationary_noise_keeps_tone():
    noise = (0.02 * rng.standard_normal(SAMPLE_RATE * 3)).astype(np.float32)
    p = Pipeline(PipelineConfig(gate_enabled=False))
    # noise only: should be attenuated significantly after adaptation
    out = run(p, noise)
    assert rms_db(out[-SAMPLE_RATE:]) < rms_db(noise[-SAMPLE_RATE:]) - 8
    # speech-like tone over noise: tone must survive
    sig = tone(1000, 2.0, 0.3) + noise[: SAMPLE_RATE * 2]
    p2 = Pipeline(PipelineConfig(gate_enabled=False))
    run(p2, noise[:SAMPLE_RATE])           # let it adapt on noise first
    o = run(p2, sig)[SAMPLE_RATE:]
    assert rms_db(o) > rms_db(tone(1000, 1.0, 0.3)) - 3


def test_learned_profile_beats_adaptive():
    noise = (0.02 * rng.standard_normal(SAMPLE_RATE * 2)).astype(np.float32)
    p = Pipeline(PipelineConfig(gate_enabled=False, highpass_hz=0))
    p.spectral.start_learning(); run(p, noise); p.spectral.finish_learning()
    out = run(p, noise)
    assert rms_db(out) < rms_db(noise) - 8


def test_latency_budget_one_frame():
    # impulse must come out within 1 frame (10 ms) + highpass delay (<1 sample)
    p = Pipeline(PipelineConfig(denoise="spectral", gate_enabled=False, highpass_hz=0, limiter_enabled=False))
    p.spectral.strength = 0.0  # unity gain path
    p.spectral.floor = 1.0
    x = np.zeros(FRAME_SIZE * 6, np.float32); x[FRAME_SIZE * 2 + 10] = 1.0
    y = run(p, x)
    assert int(np.argmax(np.abs(y))) - (FRAME_SIZE * 2 + 10) <= FRAME_SIZE


def test_realtime_factor():
    p = Pipeline()
    f = (0.05 * rng.standard_normal(FRAME_SIZE)).astype(np.float32)
    t0 = time.perf_counter()
    for _ in range(300): p.process(f)
    per_frame_ms = (time.perf_counter() - t0) / 300 * 1000
    print(f"per-frame cost: {per_frame_ms:.3f} ms of {FRAME_MS:.1f} ms budget")
    assert per_frame_ms < FRAME_MS * 0.5


def test_analyzer_peak_at_tone_freq():
    a = SpectrumAnalyzer()
    x = tone(1000, 0.1)
    for i in range(0, len(x) - FRAME_SIZE + 1, FRAME_SIZE): a.push(x[i:i + FRAME_SIZE])
    for _ in range(10): db = a.spectrum_db()
    assert abs(a.freqs[int(np.argmax(db))] - 1000) < 30


def test_i18n_fallback():
    assert tr("device.input", "id") != tr("device.input", "en")
    assert tr("nonexistent.key", "id") == "nonexistent.key"
