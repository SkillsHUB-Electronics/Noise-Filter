from dataclasses import dataclass, asdict, field
import numpy as np
from .constants import FRAME_SIZE
from .biquad import HighPass
from .eq import Equalizer
from .dynamics import Compressor, Limiter
from .gate import NoiseGate, VOCAL_RELEASE as GATE_VOCAL_RELEASE, VOCAL_FLOOR_DB as GATE_VOCAL_FLOOR_DB
from .spectral import SpectralDenoiser
from .analyzer import SpectrumAnalyzer

AI_VOCAL_MAX_WET = 0.9   # vocal mode + AI model: keep at least 10 % of the original (-20 dB) for natural harmonics


@dataclass
class PipelineConfig:
    bypass: bool = False
    highpass_hz: float = 80.0
    denoise: str = "spectral"      # "off" | "spectral" | "onnx"
    onnx_model: str = ""
    strength: float = 1.0
    vocal_mode: bool = False       # keep harmonics of speech/singing (gentler spectral denoiser + gate)
    mix: float = 1.0               # dry/wet: 1 = only the filtered signal, 0 = only the original
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
    """mic frame -> highpass -> denoise (+ dry/wet mix) -> EQ -> gate -> compressor -> gain -> limiter,
    with in/out analyzers. The dry signal for the mix is delayed by one frame, the latency of the denoisers."""

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
        self.dry = np.zeros(FRAME_SIZE, np.float32)
        self._set_vocal()
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
        if "vocal_mode" in changes:
            self._set_vocal()
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

    def _set_vocal(self) -> None:
        v = bool(self.cfg.vocal_mode)
        self.spectral.vocal = v
        self.gate.set_shape(GATE_VOCAL_RELEASE if v else 0.05, GATE_VOCAL_FLOOR_DB if v else -40.0)

    def wet_amount(self) -> float:
        """Share of the denoised signal in the output (the Mix control, capped in vocal mode with AI)."""
        m = min(max(float(self.cfg.mix), 0.0), 1.0)
        if self.cfg.vocal_mode and self.cfg.denoise == "onnx":
            m = min(m, AI_VOCAL_MAX_WET)
        return m

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
            dry, self.dry = self.dry, np.array(x, np.float32)   # x one frame ago, aligned with the denoiser output
            denoised = True
            if self.cfg.denoise == "spectral":
                x = self.spectral.process(x)
            elif self.cfg.denoise == "onnx" and self.onnx:
                x = self.onnx.process(x)
            else:
                denoised = False
            w = self.wet_amount()
            if denoised and w < 1.0:
                x = (np.float32(w) * x + np.float32(1.0 - w) * dry).astype(np.float32)
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
