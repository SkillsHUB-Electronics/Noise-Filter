import numpy as np
import pytest

from noise_filter.core import eq, Pipeline, PipelineConfig, FRAME_SIZE, SAMPLE_RATE


def run(e, x):
    return np.concatenate([e.process(x[i:i + FRAME_SIZE]) for i in range(0, len(x), FRAME_SIZE)])


def tone_gain(e, f):
    t = np.arange(SAMPLE_RATE // 2) / SAMPLE_RATE
    x = (0.3 * np.sin(2 * np.pi * f * t)).astype(np.float32)
    y = run(e, x)
    h = len(x) // 2
    return 20 * np.log10(np.std(y[h:]) / np.std(x[h:]))


@pytest.mark.parametrize("slope", eq.SLOPES)
def test_butterworth_slopes(slope):
    b = eq.band("highpass", 1000, q=0.7071, slope=slope)
    r = eq.response_db([b], np.array([1000.0, 250.0]))
    assert abs(r[0] + 3.01) < 0.05 and abs(r[1] + 2 * slope) < 1.0
    assert abs(tone_gain(eq.Equalizer(True, [b]), 1000) - r[0]) < 0.1   # curve == real audio


def test_band_types_behave():
    f = np.array([50.0, 1000.0, 10000.0])
    assert abs(eq.response_db([eq.band("peak", 1000, 6, 1)], f)[1] - 6) < 1e-6
    assert eq.response_db([eq.band("notch", 50, q=8)], f)[0] < -60
    lo = eq.response_db([eq.band("lowshelf", 200, -6)], f)
    assert abs(lo[0] + 6) < 0.5 and abs(lo[2]) < 0.1
    bp = eq.response_db([eq.band("bandpass", 1000, q=1)], f)
    assert abs(bp[1]) < 1e-6 and bp[0] < -20 and bp[2] < -15
    assert np.all(eq.response_db([eq.band("peak", 1000, 6, on=False)], f) == 0)


def test_python_loop_matches_vectorized(monkeypatch):
    x = (0.1 * np.random.default_rng(0).standard_normal(4800)).astype(np.float32)
    a = run(eq.Equalizer(True, eq.PRESETS["podcast"]), x)
    monkeypatch.setattr(eq, "_sosfilt", None)
    b = run(eq.Equalizer(True, eq.PRESETS["podcast"]), x)
    assert np.max(np.abs(a - b)) < 1e-6


def test_normalize_clamps_bad_config():
    b = eq.normalize({"type": "wobble", "freq": 1e6, "gain": 99, "q": 0, "slope": 30})
    assert b == {"type": "peak", "freq": 20000.0, "gain": 24.0, "q": 0.1, "slope": 24, "on": True}


def test_state_kept_when_dragging_a_band():
    e = eq.Equalizer(True, [eq.band("peak", 1000, 6), eq.band("highpass", 100, slope=24)])
    run(e, (0.1 * np.ones(960)).astype(np.float32))
    z = e._z.copy()
    e.set(True, [eq.band("peak", 1200, 6), eq.band("highpass", 100, slope=48)])
    assert np.array_equal(e._z[0], z[0])          # same shape: state carried
    assert len(e._z) == 1 + 4 and not e._z[1:].any()   # slope changed: fresh state


def test_presets_and_pipeline():
    for name, bands in eq.PRESETS.items():
        assert len(bands) <= eq.MAX_BANDS and all(eq.normalize(b) == b for b in bands), name
    p = Pipeline(PipelineConfig(highpass_hz=0, denoise="off", gate_enabled=False))
    sp = id(p.spectral)
    p.update(eq_enabled=True, eq_bands=[eq.band("peak", 1000, -12, 1)])
    assert id(p.spectral) == sp and p.eq.active
    t = np.arange(SAMPLE_RATE // 2) / SAMPLE_RATE
    x = (0.3 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    y = np.concatenate([p.process(x[i:i + FRAME_SIZE]) for i in range(0, len(x), FRAME_SIZE)])
    assert abs(20 * np.log10(np.std(y[len(y) // 2:]) / np.std(x[len(x) // 2:])) + 12) < 0.2


def test_combine_presets():
    P = eq.PRESETS
    a = eq.combine([P["hum_50"], P["voice_clarity"]])
    assert len(a) == 7 and [b["freq"] for b in a] == sorted(b["freq"] for b in a)
    hp = [b for b in a if b["type"] == "highpass"]
    assert len(hp) == 1 and hp[0]["freq"] == 90
    # two high-passes: keep the strictest (highest frequency, steepest slope)
    b = eq.combine([[eq.band("highpass", 80, slope=12)], [eq.band("highpass", 120, slope=36)],
                    [eq.band("lowpass", 9000, slope=24)], [eq.band("lowpass", 3400, slope=12)]])
    assert [(x["type"], x["freq"], x["slope"]) for x in b] == [("highpass", 120, 36), ("lowpass", 3400, 24)]
    # nearby peaks add up (within 1/3 octave), far ones stay separate, opposite gains cancel
    c = eq.combine([[eq.band("peak", 1000, 3, 1)], [eq.band("peak", 1100, 4, 2)], [eq.band("peak", 4000, 2)]])
    assert len(c) == 2 and abs(c[0]["gain"] - 7) < 1e-9 and abs(c[0]["freq"] - (1000 * 1100) ** 0.5) < 1e-6
    assert eq.combine([[eq.band("peak", 1000, 3)], [eq.band("peak", 1000, -3)]]) == []
    # duplicate notches kept once
    assert len(eq.combine([P["hum_50"], P["hum_50"]])) == 3
    # too many bands: refused
    many = [[eq.band("peak", 100 * 2 ** i, 3)] for i in range(9)]
    assert eq.combine(many) is None and len(eq.combine(many[:8])) == 8
    # the combined curve equals the sum of its parts when nothing overlaps
    f = np.array([70.0, 1000.0, 3000.0])
    np.testing.assert_allclose(eq.response_db(a, f),
                               eq.response_db(P["hum_50"], f) + eq.response_db(P["voice_clarity"], f), atol=1e-6)
