"""The C++ core must produce the same audio as the Python reference, frame by frame."""
import numpy as np
import pytest

from noise_filter.core import Pipeline, PipelineConfig, FRAME_SIZE, SAMPLE_RATE
from noise_filter.core import native

pytestmark = pytest.mark.skipif(not native.available(), reason=f"nf-core not built: {native.last_error()}")

TOL = 2e-4   # float32 FFT vs numpy's float64 FFT


def signal(secs=2.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(SAMPLE_RATE * secs)) / SAMPLE_RATE
    voice = 0.25 * np.sin(2 * np.pi * 220 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 1.5 * t))
    hum = 0.02 * np.sin(2 * np.pi * 50 * t)
    return (voice + hum + 0.03 * rng.standard_normal(len(t))).astype(np.float32)


def frames(x):
    for i in range(len(x) // FRAME_SIZE):
        yield x[i * FRAME_SIZE:(i + 1) * FRAME_SIZE]


def compare(py, nat, x, hook=None):
    worst = 0.0
    for i, f in enumerate(frames(x)):
        if hook:
            hook(i, py, nat)
        worst = max(worst, float(np.max(np.abs(py.process(f) - nat.process(f)))))
    return worst


@pytest.mark.parametrize("cfg", [
    PipelineConfig(),
    PipelineConfig(gate_enabled=False),
    PipelineConfig(denoise="off", highpass_hz=120.0),
    PipelineConfig(bypass=True),
    PipelineConfig(strength=1.7, gate_threshold_db=-40.0, output_gain_db=6.0),
    PipelineConfig(highpass_hz=0.0, gate_enabled=False),
], ids=["default", "nogate", "hp-only", "bypass", "strong", "spectral-only"])
def test_parity(cfg):
    x = signal()
    assert compare(Pipeline(PipelineConfig(**cfg.to_dict())), native.NativePipeline(PipelineConfig(**cfg.to_dict())), x) < TOL


def test_parity_with_learned_profile_and_live_updates():
    x = signal(3.0, seed=1)

    def hook(i, py, nat):
        if i == 10:
            py.spectral.start_learning(); nat.spectral.start_learning()
        if i == 60:
            py.spectral.finish_learning(); nat.spectral.finish_learning()
        if i == 120:
            py.update(strength=1.4, highpass_hz=150.0); nat.update(strength=1.4, highpass_hz=150.0)
        if i == 200:
            py.update(gate_threshold_db=-35.0, denoise="off"); nat.update(gate_threshold_db=-35.0, denoise="off")

    py, nat = Pipeline(), native.NativePipeline()
    assert compare(py, nat, x, hook) < TOL
    assert np.allclose(py.spectral.profile, nat.spectral.profile, rtol=1e-4, atol=1e-9)


def test_native_analyzer_matches_python():
    x = signal(0.5)
    py, nat = Pipeline(PipelineConfig(bypass=True)), native.NativePipeline(PipelineConfig(bypass=True))
    for f in frames(x):
        py.process(f); nat.process(f)
    for _ in range(40):
        a, b = py.in_analyzer.spectrum_db(), nat.in_analyzer.spectrum_db()
    loud = a > -60
    assert np.max(np.abs(a[loud] - b[loud])) < 0.05
    assert abs(py.out_analyzer.level_db() - nat.out_analyzer.level_db()) < 0.01


def test_native_is_faster():
    import time
    f = signal(0.01)[:FRAME_SIZE]
    res = {}
    for name, p in (("py", Pipeline()), ("native", native.NativePipeline())):
        for _ in range(20): p.process(f)
        t0 = time.perf_counter()
        for _ in range(300): p.process(f)
        res[name] = (time.perf_counter() - t0) / 300 * 1000
    print(f"per-frame: python {res['py']:.3f} ms, native {res['native']:.3f} ms")
    assert res["native"] < res["py"]


def test_create_pipeline_prefers_native():
    assert getattr(native.create_pipeline(PipelineConfig()), "native", False)
    assert not getattr(native.create_pipeline(PipelineConfig(), prefer_native=False), "native", False)



def _toy_recurrent_model(path):
    """frame_out = 0.5 * (frame + previous frame); the previous frame is carried as model state."""
    onnx = pytest.importorskip("onnx")
    from onnx import TensorProto, helper
    shp = [1, FRAME_SIZE]
    half = helper.make_tensor("half", TensorProto.FLOAT, [], [0.5])
    g = helper.make_graph(
        [helper.make_node("Add", ["frame", "state_in"], ["s"]),
         helper.make_node("Mul", ["s", "half"], ["frame_out"]),
         helper.make_node("Identity", ["frame"], ["state_out"])],
        "toy",
        [helper.make_tensor_value_info("frame", TensorProto.FLOAT, shp),
         helper.make_tensor_value_info("state_in", TensorProto.FLOAT, shp)],
        [helper.make_tensor_value_info("frame_out", TensorProto.FLOAT, shp),
         helper.make_tensor_value_info("state_out", TensorProto.FLOAT, shp)],
        [half])
    m = helper.make_model(g, opset_imports=[helper.make_opsetid("", 13)])
    m.ir_version = 8
    onnx.save(m, path)


def test_onnx_parity(tmp_path):
    pytest.importorskip("onnxruntime")
    if not native.has_onnx():
        pytest.skip("nf-core built without ONNX Runtime")
    path = str(tmp_path / "toy.onnx")
    _toy_recurrent_model(path)
    cfg = dict(denoise="onnx", onnx_model=path, gate_enabled=False, highpass_hz=0.0)
    py, nat = Pipeline(PipelineConfig(**cfg)), native.NativePipeline(PipelineConfig(**cfg))
    x = signal(0.5)
    assert compare(py, nat, x) < 1e-6
    # and the model really ran: output = average of this and the previous frame
    f0, f1 = list(frames(x))[:2]
    p = native.NativePipeline(PipelineConfig(**cfg))
    p.process(f0)
    np.testing.assert_allclose(p.process(f1), np.clip(0.5 * (f0 + f1), -1, 1), atol=1e-6)
