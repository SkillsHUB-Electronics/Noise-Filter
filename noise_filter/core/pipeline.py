from dataclasses import dataclass, asdict
import numpy as np
from .constants import FRAME_SIZE
from .biquad import HighPass
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

    def to_dict(self): return asdict(self)


class Pipeline:
    """mic frame -> highpass -> denoise -> gate -> gain, with in/out analyzers."""

    def __init__(self, cfg: PipelineConfig | None = None):
        self.cfg = cfg or PipelineConfig()
        self.in_analyzer = SpectrumAnalyzer()
        self.out_analyzer = SpectrumAnalyzer()
        self.apply(self.cfg)

    def apply(self, cfg: PipelineConfig) -> None:
        self.cfg = cfg
        self.hp = HighPass(cfg.highpass_hz)
        self.gate = NoiseGate(cfg.gate_threshold_db)
        self.spectral = SpectralDenoiser(strength=cfg.strength)
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
        if "gate_threshold_db" in changes:
            self.gate.threshold = 10 ** (self.cfg.gate_threshold_db / 20)
        if "onnx_model" in changes and self.cfg.onnx_model:
            from .denoiser_onnx import OnnxDenoiser
            self.onnx = OnnxDenoiser(self.cfg.onnx_model)

    def process(self, frame: np.ndarray) -> np.ndarray:
        assert frame.shape == (FRAME_SIZE,), f"expected {FRAME_SIZE} samples"
        frame = frame.astype(np.float32, copy=False)
        self.in_analyzer.push(frame)
        if self.cfg.bypass:
            out = frame
        else:
            x = self.hp.process(frame) if self.cfg.highpass_hz > 0 else frame
            if self.cfg.denoise == "spectral":
                x = self.spectral.process(x)
            elif self.cfg.denoise == "onnx" and self.onnx:
                x = self.onnx.process(x)
            if self.cfg.gate_enabled:
                x = self.gate.process(x)
            out = x * np.float32(10 ** (self.cfg.output_gain_db / 20))
        out = np.clip(out, -1.0, 1.0).astype(np.float32)
        self.out_analyzer.push(out)
        return out
