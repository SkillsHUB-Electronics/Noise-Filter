from dataclasses import dataclass, asdict, field
import numpy as np
from .constants import FRAME_SIZE
from .biquad import HighPass
from .eq import Equalizer
from .dynamics import Compressor, Limiter
from .gate import NoiseGate
from .spectral import SpectralDenoiser
from .analyzer import SpectrumAnalyzer


@dataclass
class PipelineConfig:
    bypass: bool = False
    highpass_hz: float = 80.0
    denoise: str = "spectral"      # "off" | "spectral" | "onnx"
    onnx_model: str = ""
    strength: float = 1.0
    gate_enabled: bool = True
    gate_threshold_db: float = -55.0
    output_gain_db: float = 0.0
    eq_enabled: bool = False
    eq_bands: list = field(default_factory=list)   # dicts, see core.eq
    comp_enabled: bool = False
    comp_threshold_db: float = -24.0
    comp_ratio: float = 3.0
    comp_attack_ms: float = 10.0
    comp_release_ms: float = 150.0
    comp_makeup_db: float = 0.0
    limiter_enabled: bool = True
    limiter_ceiling_db: float = -1.0

    def to_dict(self): return asdict(self)


class Pipeline:
    """mic frame -> highpass -> denoise -> EQ -> gate -> compressor -> gain -> limiter, with in/out analyzers."""

    def __init__(self, cfg: PipelineConfig | None = None):
        self.cfg = cfg or PipelineConfig()
        self.in_analyzer = SpectrumAnalyzer()
        self.out_analyzer = SpectrumAnalyzer()
        self._cap, self._cap_n = None, 0
        self.apply(self.cfg)

    def capture_start(self, max_samples: int) -> None:
        """Record the next max_samples raw input samples (for noise sample contributions)."""
        self._cap_n = 0
        self._cap = np.zeros(max(int(max_samples), 0), np.float32)

    def capture_stop(self) -> tuple[np.ndarray, int]:
        """End the recording. Returns (samples, dropped_frames); dropped is always 0 here."""
        cap, n = self._cap, self._cap_n
        self._cap, self._cap_n = None, 0
        return (cap[:n].copy() if cap is not None else np.zeros(0, np.float32)), 0

    def apply(self, cfg: PipelineConfig) -> None:
        self.cfg = cfg
        self.hp = HighPass(cfg.highpass_hz)
        self.gate = NoiseGate(cfg.gate_threshold_db)
        self.spectral = SpectralDenoiser(strength=cfg.strength)
        self.eq = Equalizer(cfg.eq_enabled, cfg.eq_bands)
        self.comp = Compressor(cfg.comp_threshold_db, cfg.comp_ratio, cfg.comp_attack_ms,
                               cfg.comp_release_ms, cfg.comp_makeup_db)
        self.limiter = Limiter(cfg.limiter_ceiling_db)
        self.onnx = None
        if cfg.denoise == "onnx" and cfg.onnx_model:
            from .denoiser_onnx import OnnxDenoiser
            self.onnx = OnnxDenoiser(cfg.onnx_model)

    def update(self, **changes) -> None:
        """Change settings live (from the UI thread) without rebuilding the chain,
        so learned noise profiles and filter states survive slider moves."""
        for k, v in changes.items():
            setattr(self.cfg, k, v)
        if "highpass_hz" in changes and self.cfg.highpass_hz > 0:
            self.hp = HighPass(self.cfg.highpass_hz)
        if "strength" in changes:
            self.spectral.strength = self.cfg.strength
        if "eq_enabled" in changes or "eq_bands" in changes:
            self.eq.set(self.cfg.eq_enabled, self.cfg.eq_bands)
        if any(k.startswith("comp_") and k != "comp_enabled" for k in changes):
            c = self.cfg
            self.comp.set(c.comp_threshold_db, c.comp_ratio, c.comp_attack_ms, c.comp_release_ms, c.comp_makeup_db)
        if "limiter_ceiling_db" in changes:
            self.limiter.set(self.cfg.limiter_ceiling_db)
        if "gate_threshold_db" in changes:
            self.gate.threshold = 10 ** (self.cfg.gate_threshold_db / 20)
        if "onnx_model" in changes and self.cfg.onnx_model:
            from .denoiser_onnx import OnnxDenoiser
            self.onnx = OnnxDenoiser(self.cfg.onnx_model)

    def dynamics_gr_db(self) -> tuple[float, float]:
        """(compressor, limiter) gain reduction in dB, for the meters."""
        return (self.comp.gr_db if self.cfg.comp_enabled else 0.0,
                self.limiter.gr_db if self.cfg.limiter_enabled else 0.0)

    def process(self, frame: np.ndarray) -> np.ndarray:
        assert frame.shape == (FRAME_SIZE,), f"expected {FRAME_SIZE} samples"
        frame = frame.astype(np.float32, copy=False)
        self.in_analyzer.push(frame)
        if self._cap is not None and self._cap_n < len(self._cap):
            k = min(FRAME_SIZE, len(self._cap) - self._cap_n)
            self._cap[self._cap_n:self._cap_n + k] = frame[:k]
            self._cap_n += k
        if self.cfg.bypass:
            out = frame
        else:
            x = self.hp.process(frame) if self.cfg.highpass_hz > 0 else frame
            if self.cfg.denoise == "spectral":
                x = self.spectral.process(x)
            elif self.cfg.denoise == "onnx" and self.onnx:
                x = self.onnx.process(x)
            x = self.eq.process(x)   # after denoising, so boosted bands do not lift the noise first
            if self.cfg.gate_enabled:
                x = self.gate.process(x)
            if self.cfg.comp_enabled:
                x = self.comp.process(x)
            out = x * np.float32(10 ** (self.cfg.output_gain_db / 20))
            if self.cfg.limiter_enabled:
                out = self.limiter.process(out)
        out = np.clip(out, -1.0, 1.0).astype(np.float32)
        self.out_analyzer.push(out)
        return out
