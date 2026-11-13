"""ctypes binding to nf-core (the C++ port of this package's core/ and the WASAPI engine).

The native pipeline has the same surface as core.Pipeline (cfg, update, process,
in_analyzer/out_analyzer, spectral.start_learning/finish_learning), so the UI can use
either one. Build the library with:

    cmake -S cpp -B cpp/build && cmake --build cpp/build --config Release && cmake --install cpp/build

which copies nf_core.dll / libnf_core.so into noise_filter/_native/. Set NF_CORE_LIB to
use a library somewhere else, or NF_CORE_DISABLE=1 to force the pure Python path.
"""
from __future__ import annotations

import ctypes as C
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .constants import FRAME_SIZE, SAMPLE_RATE
from .pipeline import PipelineConfig

_MODES = {"off": 0, "spectral": 1, "onnx": 2}


class _Config(C.Structure):
    _fields_ = [("bypass", C.c_int), ("highpass_hz", C.c_float), ("denoise", C.c_int),
                ("strength", C.c_float), ("gate_enabled", C.c_int), ("gate_threshold_db", C.c_float),
                ("output_gain_db", C.c_float)]


class _DeviceInfo(C.Structure):
    _fields_ = [("id", C.c_char * 512), ("name", C.c_char * 256), ("is_default", C.c_int)]


class _Stats(C.Structure):
    _fields_ = [("frames", C.c_longlong), ("xruns", C.c_longlong), ("dsp_avg_us", C.c_float),
                ("dsp_max_us", C.c_float), ("latency_ms", C.c_float)]


_lib = None
_load_error = ""


def _candidates():
    env = os.environ.get("NF_CORE_LIB")
    if env:
        yield Path(env)
    names = {"win32": ["nf_core.dll", "libnf_core.dll"], "darwin": ["libnf_core.dylib"]}.get(
        sys.platform, ["libnf_core.so"])
    here = Path(__file__).resolve().parent.parent
    for d in (here / "_native", here.parent / "cpp" / "build", here.parent / "cpp" / "build" / "Release"):
        for n in names:
            yield d / n


def load_library():
    """Return the loaded nf-core library, or None (see last_error())."""
    global _lib, _load_error
    if _lib is not None or os.environ.get("NF_CORE_DISABLE") == "1":
        return _lib
    for path in _candidates():
        if not path.is_file():
            continue
        try:
            if sys.platform == "win32":
                os.add_dll_directory(str(path.parent))   # onnxruntime.dll may sit next to it
            lib = C.CDLL(str(path))
        except OSError as e:
            _load_error = f"{path}: {e}"
            continue
        _declare(lib)
        if lib.nf_api_version() != 1 or lib.nf_frame_size() != FRAME_SIZE:
            _load_error = f"{path}: incompatible nf-core build"
            continue
        _lib = lib
        return _lib
    _load_error = _load_error or "nf-core library not found (build it with CMake, see cpp/README.md)"
    return None


def available() -> bool:
    return load_library() is not None


def has_onnx() -> bool:
    lib = load_library()
    return bool(lib and lib.nf_has_onnx())


def last_error() -> str:
    return _load_error


def _declare(lib):
    P, F, I, V = C.c_void_p, C.POINTER(C.c_float), C.c_int, None
    sig = {
        "nf_api_version": ([], I), "nf_frame_size": ([], I), "nf_sample_rate": ([], I),
        "nf_analyzer_bins": ([], I), "nf_profile_bins": ([], I), "nf_has_onnx": ([], I),
        "nf_pipeline_create": ([C.POINTER(_Config)], P), "nf_pipeline_destroy": ([P], V),
        "nf_pipeline_set_config": ([P, C.POINTER(_Config)], V),
        "nf_pipeline_get_config": ([P, C.POINTER(_Config)], V),
        "nf_pipeline_set_spectral_params": ([P, C.c_float, C.c_float, C.c_float], V),
        "nf_pipeline_load_onnx": ([P, C.c_char_p, C.c_char_p, I], I),
        "nf_pipeline_process": ([P, F, F], I),
        "nf_pipeline_learn_start": ([P], V), "nf_pipeline_learn_finish": ([P], V),
        "nf_pipeline_clear_profile": ([P], V),
        "nf_pipeline_capture_start": ([P, I], V),
        "nf_pipeline_capture_stop": ([P, F, I, C.POINTER(I)], I),
        "nf_pipeline_get_profile": ([P, F], I), "nf_pipeline_set_profile": ([P, F], V),
        "nf_pipeline_spectrum_db": ([P, I, F], V), "nf_pipeline_level_db": ([P, I], C.c_float),
        "nf_device_count": ([I], I), "nf_device_get": ([I, I, C.POINTER(_DeviceInfo)], I),
        "nf_engine_create": ([P, C.c_char_p, C.c_char_p, I, C.c_char_p, I], P),
        "nf_engine_start": ([P, C.c_char_p, I], I), "nf_engine_stop": ([P], V),
        "nf_engine_destroy": ([P], V), "nf_engine_get_stats": ([P, C.POINTER(_Stats)], V),
    }
    for name, (args, res) in sig.items():
        fn = getattr(lib, name)
        fn.argtypes, fn.restype = args, res


def _fptr(a: np.ndarray):
    return a.ctypes.data_as(C.POINTER(C.c_float))


def _to_c(cfg: PipelineConfig) -> _Config:
    return _Config(int(cfg.bypass), float(cfg.highpass_hz), _MODES.get(cfg.denoise, 1), float(cfg.strength),
                   int(cfg.gate_enabled), float(cfg.gate_threshold_db), float(cfg.output_gain_db))


class NativeAnalyzer:
    def __init__(self, lib, handle, which: int):
        self._lib, self._h, self._which = lib, handle, which
        self.size = 2048
        self.freqs = np.fft.rfftfreq(self.size, 1 / SAMPLE_RATE)
        self.db = np.full(lib.nf_analyzer_bins(), -120.0, np.float32)

    def spectrum_db(self) -> np.ndarray:
        self._lib.nf_pipeline_spectrum_db(self._h, self._which, _fptr(self.db))
        return self.db

    def level_db(self) -> float:
        return float(self._lib.nf_pipeline_level_db(self._h, self._which))


class NativeSpectral:
    """Mirrors the parts of SpectralDenoiser the app and tests use."""

    def __init__(self, lib, handle, strength: float):
        self._lib, self._h = lib, handle
        self._floor, self._smoothing, self._rise = 0.08, 0.6, 0.003
        self._strength = strength
        self._owner = None   # set by NativePipeline so strength edits go through its config

    def start_learning(self): self._lib.nf_pipeline_learn_start(self._h)
    def finish_learning(self): self._lib.nf_pipeline_learn_finish(self._h)
    def clear_profile(self): self._lib.nf_pipeline_clear_profile(self._h)

    @property
    def profile(self):
        out = np.zeros(self._lib.nf_profile_bins(), np.float32)
        return out if self._lib.nf_pipeline_get_profile(self._h, _fptr(out)) else None

    @profile.setter
    def profile(self, p):
        if p is None:
            self.clear_profile()
        else:
            arr = np.ascontiguousarray(p, np.float32)
            assert arr.shape == (self._lib.nf_profile_bins(),)
            self._lib.nf_pipeline_set_profile(self._h, _fptr(arr))

    def _push(self):
        self._lib.nf_pipeline_set_spectral_params(self._h, self._floor, self._smoothing, self._rise)

    floor = property(lambda s: s._floor, lambda s, v: (setattr(s, "_floor", float(v)), s._push()))
    smoothing = property(lambda s: s._smoothing, lambda s, v: (setattr(s, "_smoothing", float(v)), s._push()))
    rise = property(lambda s: s._rise, lambda s, v: (setattr(s, "_rise", float(v)), s._push()))

    @property
    def strength(self): return self._owner.cfg.strength if self._owner else self._strength

    @strength.setter
    def strength(self, v):
        if self._owner:
            self._owner.update(strength=float(v))
        self._strength = float(v)


class NativePipeline:
    """Drop-in replacement for core.Pipeline backed by nf-core."""

    native = True

    def __init__(self, cfg: PipelineConfig | None = None):
        lib = load_library()
        if lib is None:
            raise RuntimeError(last_error())
        self._lib = lib
        self.cfg = cfg or PipelineConfig()
        c = _to_c(self.cfg)
        self._h = lib.nf_pipeline_create(C.byref(c))
        if not self._h:
            raise RuntimeError("nf_pipeline_create failed")
        self.in_analyzer = NativeAnalyzer(lib, self._h, 0)
        self.out_analyzer = NativeAnalyzer(lib, self._h, 1)
        self.spectral = NativeSpectral(lib, self._h, self.cfg.strength)
        self.spectral._owner = self
        self._out = np.zeros(FRAME_SIZE, np.float32)
        if self.cfg.denoise == "onnx" and self.cfg.onnx_model:
            self._load_onnx(self.cfg.onnx_model)

    def _load_onnx(self, path: str):
        err = C.create_string_buffer(512)
        if self._lib.nf_pipeline_load_onnx(self._h, path.encode("utf-8"), err, 512) != 0:
            raise RuntimeError(err.value.decode("utf-8", "replace"))

    def apply(self, cfg: PipelineConfig) -> None:
        self.cfg = cfg
        self._lib.nf_pipeline_set_config(self._h, C.byref(_to_c(cfg)))
        if cfg.denoise == "onnx" and cfg.onnx_model:
            self._load_onnx(cfg.onnx_model)

    def update(self, **changes) -> None:
        for k, v in changes.items():
            setattr(self.cfg, k, v)
        self._lib.nf_pipeline_set_config(self._h, C.byref(_to_c(self.cfg)))
        if "onnx_model" in changes and self.cfg.onnx_model:
            self._load_onnx(self.cfg.onnx_model)

    def capture_start(self, max_samples: int) -> None:
        self._cap_max = max(int(max_samples), 0)
        self._lib.nf_pipeline_capture_start(self._h, self._cap_max)

    def capture_stop(self) -> tuple[np.ndarray, int]:
        out = np.zeros(getattr(self, "_cap_max", 0), np.float32)
        dropped = C.c_int(0)
        n = self._lib.nf_pipeline_capture_stop(self._h, _fptr(out), len(out), C.byref(dropped))
        return out[:n].copy(), int(dropped.value)

    def process(self, frame: np.ndarray) -> np.ndarray:
        assert frame.shape == (FRAME_SIZE,), f"expected {FRAME_SIZE} samples"
        x = np.ascontiguousarray(frame, np.float32)
        out = np.empty(FRAME_SIZE, np.float32)
        self._lib.nf_pipeline_process(self._h, _fptr(x), _fptr(out))
        return out

    @property
    def handle(self):
        return self._h

    def __del__(self):
        h, self._h = getattr(self, "_h", None), None
        if h and self._lib:
            self._lib.nf_pipeline_destroy(h)


@dataclass
class NativeDevice:
    index: int
    name: str
    id: str
    is_default: bool = False


def list_devices(kind: str = "input") -> list[NativeDevice]:
    lib = load_library()
    if lib is None:
        return []
    k = 0 if kind == "input" else 1
    out = []
    for i in range(lib.nf_device_count(k)):
        d = _DeviceInfo()
        if lib.nf_device_get(k, i, C.byref(d)) == 0:
            out.append(NativeDevice(i, d.name.decode("utf-8", "replace"), d.id.decode("utf-8"), bool(d.is_default)))
    return out


class NativeEngine:
    """C++ WASAPI engine: capture, filter and render all happen on a native MMCSS thread,
    so Python's GIL and garbage collector never touch the audio path."""

    def __init__(self, pipeline: NativePipeline, in_id: str | None, out_id: str | None, exclusive: bool = False):
        self._lib, self.pipe = pipeline._lib, pipeline
        err = C.create_string_buffer(512)
        self._h = self._lib.nf_engine_create(pipeline.handle, (in_id or "").encode(), (out_id or "").encode(),
                                             int(exclusive), err, 512)
        if not self._h:
            raise RuntimeError(err.value.decode("utf-8", "replace"))

    def start(self):
        err = C.create_string_buffer(512)
        if self._lib.nf_engine_start(self._h, err, 512) != 0:
            raise RuntimeError(err.value.decode("utf-8", "replace"))

    def stop(self):
        if self._h:
            self._lib.nf_engine_destroy(self._h)
            self._h = None

    def stats(self) -> dict:
        s = _Stats()
        if self._h:
            self._lib.nf_engine_get_stats(self._h, C.byref(s))
        return {k: getattr(s, k) for k, _ in _Stats._fields_}

    @property
    def xruns(self) -> int:
        return int(self.stats()["xruns"])


def create_pipeline(cfg: PipelineConfig | None = None, prefer_native: bool = True):
    """Native pipeline when the library is present (and supports the chosen mode), else Python."""
    from .pipeline import Pipeline
    cfg = cfg or PipelineConfig()
    if prefer_native and available() and (cfg.denoise != "onnx" or has_onnx()):
        try:
            return NativePipeline(cfg)
        except Exception:
            pass
    return Pipeline(cfg)
