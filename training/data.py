"""Training data: random (clean speech + noise) mixtures at 48 kHz, generated on the fly.

Clean speech and noise come from folders of audio files (wav / flac / ogg, any sample rate,
mixed to mono). Noise contributed by users later (F3) is just another noise folder.
`SyntheticSource` makes speech-like and noise-like signals without any download, used by the
tests and for a quick smoke run.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from math import gcd
from pathlib import Path

import numpy as np

SR = 48_000
AUDIO_EXT = {".wav", ".flac", ".ogg"}


def list_audio(dirs) -> list[Path]:
    files = []
    for d in dirs or []:
        files += [p for p in Path(d).rglob("*") if p.suffix.lower() in AUDIO_EXT]
    return sorted(files)


class FileSource:
    """Random fixed-length segments from audio files, resampled to 48 kHz."""

    def __init__(self, files: list[Path], min_seconds: float = 0.5, preload_gb: float = 6.0):
        import soundfile as sf
        self.sf = sf
        self.items = []
        for f in files:
            try:
                info = sf.info(str(f))
            except Exception:
                continue
            if info.frames / info.samplerate >= min_seconds:
                self.items.append((f, info.frames, info.samplerate))
        if not self.items:
            raise ValueError("no usable audio files")
        # Keep 48 kHz data in RAM as int16 when it fits: random segment reads become free.
        self.cache = None
        total = sum(fr for _, fr, sr in self.items if sr == SR) * 2 / 1e9
        if total <= preload_gb and all(sr == SR for _, _, sr in self.items):
            self.cache = [sf.read(str(f), dtype="int16", always_2d=True)[0].mean(1).astype(np.int16)
                          for f, _, _ in self.items]

    def __len__(self):
        return len(self.items)

    def segment(self, n: int, rng: random.Random) -> np.ndarray:
        from scipy.signal import resample_poly
        i = rng.randrange(len(self.items))
        if self.cache is not None:
            a = self.cache[i]
            if len(a) <= n:
                a = np.tile(a, n // max(len(a), 1) + 1)
            start = rng.randrange(len(a) - n + 1)
            return a[start:start + n].astype(np.float32) / 32768.0
        f, frames, sr = self.items[i]
        need = int(np.ceil(n * sr / SR)) + 8
        if frames <= need:
            x, _ = self.sf.read(str(f), dtype="float32", always_2d=True)
            x = np.tile(x, (need // max(len(x), 1) + 1, 1))[:need]
        else:
            start = rng.randrange(frames - need)
            x, _ = self.sf.read(str(f), start=start, frames=need, dtype="float32", always_2d=True)
        x = x.mean(1)
        if sr != SR:
            g = gcd(SR, sr)
            x = resample_poly(x, SR // g, sr // g).astype(np.float32)
        x = x[:n]
        if len(x) < n:
            x = np.pad(x, (0, n - len(x)))
        return x.astype(np.float32)


class SyntheticSource:
    """No-download stand-in: 'speech' = harmonic voice with moving pitch, formants and pauses;
    'noise' = white / pink / brown / hum / fan / babble-like mixtures."""

    def __init__(self, kind: str):
        assert kind in ("speech", "noise")
        self.kind = kind

    def __len__(self):
        return 1_000_000

    def segment(self, n: int, rng: random.Random) -> np.ndarray:
        r = np.random.default_rng(rng.randrange(1 << 30))
        t = np.arange(n) / SR
        if self.kind == "speech":
            return _synthetic_speech(n, t, r)
        return _synthetic_noise(n, t, r)


def _colored(n, r, slope):
    spec = np.fft.rfft(r.standard_normal(n))
    f = np.maximum(np.fft.rfftfreq(n, 1 / SR), 20.0)
    x = np.fft.irfft(spec / f ** (slope / 2), n)
    return x / (np.std(x) + 1e-9)


def _synthetic_speech(n, t, r):
    f0 = r.uniform(90, 250) * (1 + 0.15 * np.sin(2 * np.pi * r.uniform(0.5, 3) * t + r.uniform(0, 6)))
    phase = 2 * np.pi * np.cumsum(f0) / SR
    formants = r.uniform([300, 900, 2200], [900, 2200, 3500])
    x = np.zeros(n)
    for h in range(1, 40):
        fh = f0 * h
        amp = sum(np.exp(-((fh - fm) / 150.0) ** 2) for fm in formants) + 0.02
        x += amp * np.sin(h * phase) * (fh < 12000)
    x += 0.05 * _colored(n, r, 0) * (r.random() < 0.5)          # some breath / fricative noise
    syll = (np.sin(2 * np.pi * r.uniform(2, 5) * t + r.uniform(0, 6)) > r.uniform(-0.3, 0.4)).astype(float)
    k = np.hanning(int(0.03 * SR))
    env = np.convolve(syll, k / k.sum(), "same")
    x *= env
    return (x / (np.std(x) + 1e-9)).astype(np.float32)


def _synthetic_noise(n, t, r):
    kind = r.integers(0, 6)
    if kind == 0:
        x = _colored(n, r, 0)
    elif kind == 1:
        x = _colored(n, r, 1)
    elif kind == 2:
        x = _colored(n, r, 2)
    elif kind == 3:  # mains hum + harmonics
        f = r.choice([50.0, 60.0])
        x = sum(np.sin(2 * np.pi * f * h * t + r.uniform(0, 6)) / h for h in range(1, 8)) + 0.1 * _colored(n, r, 1)
    elif kind == 4:  # fan / AC: broadband + tonal blade-pass
        x = _colored(n, r, 1) + 0.5 * np.sin(2 * np.pi * r.uniform(80, 400) * t)
    else:            # babble-ish: several synthetic voices
        x = sum(_synthetic_speech(n, t, r) for _ in range(4))
    return (x / (np.std(x) + 1e-9)).astype(np.float32)


@dataclass
class MixConfig:
    seconds: float = 2.0
    snr_db: tuple = (-5.0, 20.0)
    speech_dbfs: tuple = (-38.0, -16.0)
    p_clean_only: float = 0.08
    p_noise_only: float = 0.05


def rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)


def make_mix(clean_src, noise_src, cfg: MixConfig, rng: random.Random):
    """Returns (noisy, clean) float32 arrays, length a multiple of 480 samples."""
    n = int(cfg.seconds * SR) // 480 * 480
    s = clean_src.segment(n, rng)
    v = noise_src.segment(n, rng)
    if rng.random() < 0.5:          # second noise layer for variety
        v = v + noise_src.segment(n, rng) * rng.uniform(0.2, 1.0)
    s = s / (np.sqrt(np.mean(s ** 2)) + 1e-9) * 10 ** (rng.uniform(*cfg.speech_dbfs) / 20)
    u = rng.random()
    if u < cfg.p_clean_only:
        v = np.zeros_like(v)
    else:
        snr = rng.uniform(*cfg.snr_db)
        v = v / (np.sqrt(np.mean(v ** 2)) + 1e-9) * np.sqrt(np.mean(s ** 2)) * 10 ** (-snr / 20)
        if u < cfg.p_clean_only + cfg.p_noise_only:
            v = v * 10 ** (rng.uniform(-6, 6) / 20)
            s = np.zeros_like(s)
    x = s + v
    peak = np.max(np.abs(x))
    if peak > 0.98:
        x, s = x / peak * 0.98, s / peak * 0.98
    return x.astype(np.float32), s.astype(np.float32)


def build_sources(clean_dirs, noise_dirs, synthetic: bool, holdout: float = 0.05, seed: int = 0):
    """(train_clean, train_noise, val_clean, val_noise). Files are split so validation uses unseen files."""
    if synthetic:
        return (SyntheticSource("speech"), SyntheticSource("noise"),
                SyntheticSource("speech"), SyntheticSource("noise"))
    out = []
    for dirs in (clean_dirs, noise_dirs):
        files = list_audio(dirs)
        if not files:
            raise SystemExit(f"no audio files found in {dirs}")
        random.Random(seed).shuffle(files)
        k = max(1, int(len(files) * holdout))
        out.append((files[k:], files[:k]))
    (ct, cv), (nt, nv) = out
    return FileSource(ct), FileSource(nt), FileSource(cv), FileSource(nv)
