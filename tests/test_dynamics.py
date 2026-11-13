import numpy as np

from noise_filter.core import Pipeline, PipelineConfig, FRAME_SIZE, SAMPLE_RATE
from noise_filter.core.dynamics import Compressor, Limiter, static_curve_db


def run(proc, x):
    return np.concatenate([proc(x[i:i + FRAME_SIZE]) for i in range(0, len(x), FRAME_SIZE)])


def tone(amp, secs=0.5, f=1000):
    t = np.arange(int(SAMPLE_RATE * secs)) / SAMPLE_RATE
    return (amp * np.sin(2 * np.pi * f * t)).astype(np.float32)


def db(x):
    return 20 * np.log10(np.sqrt(np.mean(x.astype(np.float64) ** 2)) + 1e-12)


def test_static_curve_soft_knee():
    y = static_curve_db([-40, -20, 0], -20, 4)
    assert y[0] == -40 and y[2] == -15
    assert -20 > y[1] > -21          # inside the knee: gently compressed
    k = static_curve_db(np.linspace(-30, -10, 201), -20, 4)
    assert np.all(np.diff(k) > 0)    # monotonic, no step at the knee


def test_compressor_evens_out_levels():
    c = Compressor(threshold_db=-30, ratio=4, attack_ms=5, release_ms=100)
    loud, quiet = run(c.process, tone(0.9)), None
    c2 = Compressor(threshold_db=-30, ratio=4, attack_ms=5, release_ms=100)
    quiet = run(c2.process, tone(0.01))
    h = len(loud) // 2
    in_gap = db(tone(0.9)[h:]) - db(tone(0.01)[h:])
    out_gap = db(loud[h:]) - db(quiet[h:])
    assert out_gap < in_gap - 15 and c.gr_db > 10 and c2.gr_db == 0.0


def test_makeup_gain():
    c = Compressor(threshold_db=0, ratio=1, makeup_db=6)
    y = run(c.process, tone(0.1))
    assert abs(db(y) - db(tone(0.1)) - 6) < 0.01


def test_limiter_never_exceeds_ceiling_and_has_no_delay():
    l = Limiter(-3.0)
    x = tone(1.0)
    y = run(l.process, x)
    assert np.max(np.abs(y)) <= 10 ** (-3 / 20) + 1e-6
    imp = np.zeros(FRAME_SIZE, np.float32); imp[100] = 1.0
    out = Limiter(-3.0).process(imp)                              # zero look-ahead: same sample
    assert np.flatnonzero(out).tolist() == [100] and abs(out[100] - 10 ** (-3 / 20)) < 1e-6
    q = tone(0.05)
    assert np.array_equal(run(Limiter(-1.0).process, q), q)


def test_pipeline_chain_and_meters():
    cfg = PipelineConfig(highpass_hz=0, denoise="off", gate_enabled=False, output_gain_db=12.0)
    p = Pipeline(cfg)
    y = run(p.process, tone(0.8))
    assert np.max(np.abs(y)) <= 10 ** (-1 / 20) + 1e-6          # default limiter catches the +12 dB
    assert p.dynamics_gr_db()[1] > 5 and p.dynamics_gr_db()[0] == 0.0
    p.update(comp_enabled=True, comp_threshold_db=-30.0, comp_ratio=8.0)
    run(p.process, tone(0.8))
    assert p.comp.ratio == 8.0 and p.dynamics_gr_db()[0] > 10
    p.update(limiter_enabled=False, output_gain_db=0.0, comp_enabled=False)
    y = run(p.process, tone(0.5))
    assert abs(np.max(np.abs(y)) - 0.5) < 1e-3
