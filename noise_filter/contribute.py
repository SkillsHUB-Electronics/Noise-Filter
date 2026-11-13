"""Opt-in noise sample contributions (F3).

After "Learn noise" the app has a few seconds of room noise. If the user agrees, that recording
is sent to the sample intake service and, after screening and the developer's review, used to
train the next AI model. Users can also send noise from an audio file they recorded themselves
(source "file"): it is converted to 48 kHz mono, cut into clips of at most 10 s and every clip
goes through the same checks.

Privacy rules enforced here (and again by CI before a sample can reach training):
  - a recording that contains anything that looks like a human voice is never offered;
  - only the audio, the noise category, the app version, the OS and a random installation id
    are sent; nothing that identifies the person or the PC;
  - the user hears/approves every sample; there is no automatic sending.
"""
from __future__ import annotations

import io
import json
import os
import platform
import uuid
import wave
from pathlib import Path

import numpy as np

from . import __version__

SR = 48_000
SAMPLES_URL = os.environ.get(
    "NF_SAMPLES_URL", "https://noise-filter-samples.mukhamadkhoirul.workers.dev")   # empty = feature off
CATEGORIES = ["fan_ac", "traffic", "keyboard", "crowd", "machine", "rain_wind", "other"]
CONSENT = "cc0-v1"
TRIM_START = 0.25       # seconds dropped at the start (button click, engine settling)
MIN_SECONDS = 2.0
MAX_SECONDS = 10.0
SOURCES = ["mic", "file"]
MAX_FILE_CLIPS = 5          # the intake service accepts 5 uploads per installation per minute
MAX_FILE_SECONDS = 600      # longer files are refused (decoding them would take too much memory)
MAX_FILE_BYTES = 200 * 1024 * 1024


def enabled() -> bool:
    return SAMPLES_URL.startswith("https://")


# ---------------------------------------------------------------------------------------------
# Screening

def _frames(x: np.ndarray, n: int) -> np.ndarray:
    k = len(x) // n
    return x[:k * n].reshape(k, n).astype(np.float64)


def _bandpass(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Zero-phase FFT band-pass (numpy only: the installer does not ship scipy)."""
    X = np.fft.rfft(np.asarray(x, np.float64))
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, len(x))


def voiced_frames(x: np.ndarray, frame: int = 1920) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per 40 ms frame: (periodicity 0..1, pitch Hz, band energy dB) of the 80-3400 Hz band.

    Periodicity is the normalised autocorrelation peak for lags of 80-400 Hz (human pitch),
    computed on a 12 kHz copy to keep it cheap."""
    y = _bandpass(x, 80.0, 3400.0)[::4]                           # band-limited, so 12 kHz is alias-free
    sr, n = SR // 4, frame // 4
    lo, hi = sr // 400, sr // 80
    per, pitch, energy = [], [], []
    for f in _frames(y, n):
        f = f - f.mean()
        e = float(np.dot(f, f))
        energy.append(10 * np.log10(e / len(f) + 1e-12))
        if e < 1e-10:
            per.append(0.0); pitch.append(0.0)
            continue
        ac = np.correlate(f, f, "full")[len(f) - 1:]
        # normalise by the overlap so long lags are not penalised
        ac = ac / (e * (1 - np.arange(len(ac)) / len(f)) + 1e-12)
        lag = lo + int(np.argmax(ac[lo:hi]))
        # a real pitch peak sits after a dip; low-frequency rumble just decays slowly from lag 0
        real = lo < lag < hi - 1 and np.min(ac[:lag]) < ac[lag] - 0.4
        per.append(float(ac[lag]) if real else 0.0); pitch.append(sr / lag)
    return np.array(per), np.array(pitch), np.array(energy)


def looks_like_speech(x: np.ndarray) -> bool:
    """Conservative voice detector: when in doubt, say yes (the sample is then not offered).

    Speech = voiced (periodic at 80-400 Hz) frames that either stand out from the background
    (louder than the recording's typical level) or form a pitch track that moves, as speech
    pitch does. A fan or mains hum is periodic too, but steady in level and pitch. Some
    rumbly or babble-like noises are rejected too; losing those samples is the price of
    never sending a voice."""
    per, pitch, energy = voiced_frames(x)
    if len(per) == 0:
        return False
    voiced = per > 0.5
    loud = energy > np.median(energy) + 4.0
    run = 0
    for v in voiced & loud:                  # 2 frames = 80 ms of voice above the background
        run = run + 1 if v else 0
        if run >= 2:
            return True
    if voiced.mean() > 0.08:
        p = pitch[voiced]
        if np.std(np.log2(p)) > 0.05:        # pitch moving by more than ~4 %: intonation
            return True
    return False


def model_keeps_voice(x: np.ndarray, model_path: str | None = None, window: float = 0.2,
                      threshold_db: float = -12.0) -> bool | None:
    """Second opinion from the AI denoiser: it is trained to keep speech and remove noise, so
    if any 200 ms window keeps much of its energy after denoising, something voice-like is there.
    None when no model / engine is available."""
    from .core import FRAME_SIZE, PipelineConfig
    from .core import native
    from .model_update import current_model_path
    path = model_path or current_model_path()
    if not path:
        return None
    try:
        p = native.create_pipeline(PipelineConfig(denoise="onnx", onnx_model=path, gate_enabled=False,
                                                  highpass_hz=80.0))
        x = np.asarray(x, np.float32)
        n = len(x) // FRAME_SIZE * FRAME_SIZE
        y = np.concatenate([p.process(x[i:i + FRAME_SIZE]) for i in range(0, n, FRAME_SIZE)])
    except Exception:
        return None
    y = y[FRAME_SIZE:]                       # one frame of delay
    x = x[:len(y)]
    w = int(window * SR)
    skip = int(0.3 * SR)                     # let the model's state settle
    ex, ey = _frames(x[skip:], w), _frames(y[skip:], w)
    if len(ex) == 0:
        return None
    ratio = 10 * np.log10((ey ** 2).mean(1) + 1e-12) - 10 * np.log10((ex ** 2).mean(1) + 1e-12)
    return bool(np.max(ratio) > threshold_db)


def check_sample(x: np.ndarray, model_path: str | None = None) -> tuple[bool, str]:
    """(ok, reason). ok=False means: do not offer this recording."""
    x = np.asarray(x, np.float32)
    if len(x) < MIN_SECONDS * SR:
        return False, "too short"
    if np.max(np.abs(x)) >= 0.99:
        return False, "clipped"
    rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
    if 20 * np.log10(rms + 1e-12) < -70:
        return False, "silent"
    if looks_like_speech(x) or model_keeps_voice(x, model_path):
        return False, "speech"
    return True, "ok"


def prepare(raw: np.ndarray, dropped: int = 0) -> np.ndarray | None:
    """Trim the start and cap the length of a 'Learn noise' recording; None if unusable."""
    if dropped:
        return None                              # the recording has gaps
    x = np.asarray(raw, np.float32)[int(TRIM_START * SR):int(MAX_SECONDS * SR)]
    ok, _ = check_sample(x)
    return x if ok else None


# ---------------------------------------------------------------------------------------------
# Audio files chosen by the user

class AudioFileError(ValueError):
    """The file cannot be used; str(e) is a short reason key: unsupported, too_long, too_short, empty."""


def parse_wav(data: bytes) -> tuple[np.ndarray, int]:
    """Decode a WAV file (PCM 8/16/24/32-bit, float 32/64, extensible) -> (mono float32, rate)."""
    if len(data) < 12 or data[:4] not in (b"RIFF", b"RF64") or data[8:12] != b"WAVE":
        raise AudioFileError("unsupported")
    o, fmt = 12, None
    while o + 8 <= len(data):
        cid, size = data[o:o + 4], int.from_bytes(data[o + 4:o + 8], "little")
        body = data[o + 8:o + 8 + size]
        if cid == b"fmt " and len(body) >= 16:
            tag, ch, rate = (int.from_bytes(body[0:2], "little"), int.from_bytes(body[2:4], "little"),
                             int.from_bytes(body[4:8], "little"))
            bits = int.from_bytes(body[14:16], "little")
            if tag == 0xFFFE and len(body) >= 26:          # WAVE_FORMAT_EXTENSIBLE: real tag in the GUID
                tag = int.from_bytes(body[24:26], "little")
            fmt = (tag, ch, rate, bits)
        elif cid == b"data" and fmt:
            tag, ch, rate, bits = fmt
            if ch < 1 or not 8000 <= rate <= 384000:
                raise AudioFileError("unsupported")
            if size == 0xFFFFFFFF or o + 8 + size > len(data):   # streamed / RF64: data runs to the end
                body = data[o + 8:]
            width = bits // 8
            body = body[:len(body) // (width * ch) * width * ch]
            if tag == 1 and bits == 8:
                x = (np.frombuffer(body, np.uint8).astype(np.float32) - 128) / 128
            elif tag == 1 and bits == 16:
                x = np.frombuffer(body, "<i2").astype(np.float32) / 32768
            elif tag == 1 and bits == 24:
                b = np.frombuffer(body, np.uint8).reshape(-1, 3).astype(np.int32)
                v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
                x = (np.where(v >= 1 << 23, v - (1 << 24), v)).astype(np.float32) / (1 << 23)
            elif tag == 1 and bits == 32:
                x = (np.frombuffer(body, "<i4").astype(np.float64) / 2 ** 31).astype(np.float32)
            elif tag == 3 and bits in (32, 64):
                x = np.frombuffer(body, "<f4" if bits == 32 else "<f8").astype(np.float32)
            else:
                raise AudioFileError("unsupported")
            return x.reshape(-1, ch).mean(1).astype(np.float32), rate
        o += 8 + size + (size & 1)
    raise AudioFileError("unsupported")


def resample(x: np.ndarray, rate: int, target: int = SR) -> np.ndarray:
    """Band-limited resampling by FFT (numpy only). Fine for clips of a few minutes."""
    x = np.asarray(x, np.float32)
    if rate == target or len(x) == 0:
        return x
    n = int(round(len(x) * target / rate))
    X = np.fft.rfft(x.astype(np.float64))
    m = n // 2 + 1
    Y = np.zeros(m, complex)
    k = min(m, len(X))
    Y[:k] = X[:k]
    return (np.fft.irfft(Y, n) * (n / len(x))).astype(np.float32)


def load_audio_file(path: str | os.PathLike, decoder=None) -> np.ndarray:
    """Read an audio file as 48 kHz mono float32. WAV is decoded here; other formats (MP3, M4A,
    FLAC, OGG...) need `decoder(path) -> (mono float32, rate)`, which the UI provides."""
    p = Path(path)
    if p.stat().st_size > MAX_FILE_BYTES:
        raise AudioFileError("too_long")
    if p.suffix.lower() in (".wav", ".wave"):
        x, rate = parse_wav(p.read_bytes())
    elif decoder is not None:
        x, rate = decoder(str(p))
    else:
        raise AudioFileError("unsupported")
    if len(x) == 0:
        raise AudioFileError("empty")
    if len(x) > MAX_FILE_SECONDS * rate:
        raise AudioFileError("too_long")
    if len(x) < MIN_SECONDS * rate:
        raise AudioFileError("too_short")
    return resample(x, rate)


def file_clips(x: np.ndarray, model_path: str | None = None,
               max_clips: int = MAX_FILE_CLIPS) -> tuple[list[np.ndarray], dict]:
    """Cut a file into up to `max_clips` clips of at most 10 s, spread evenly over the file, and
    keep the ones that pass check_sample. Returns (clips, {reason: count} of the dropped ones)."""
    x = np.asarray(x, np.float32)
    n = int(MAX_SECONDS * SR)
    if len(x) <= n:
        starts = [0]
    else:
        count = min(max_clips, len(x) // n)
        starts = np.linspace(0, len(x) - n, count).astype(int).tolist()
    clips, dropped = [], {}
    for s0 in starts:
        c = x[s0:s0 + n]
        ok, reason = check_sample(c, model_path)
        if ok:
            clips.append(c)
        else:
            dropped[reason] = dropped.get(reason, 0) + 1
    return clips, dropped


# ---------------------------------------------------------------------------------------------
# Upload

def encode_wav(x: np.ndarray) -> bytes:
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm)
    return b.getvalue()


def _state_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "NoiseFilter" / "contribute.json"


def load_state() -> dict:
    try:
        return json.loads(_state_path().read_text("utf-8"))
    except Exception:
        return {}


def save_state(**changes) -> dict:
    s = {**load_state(), **changes}
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(s, indent=2), "utf-8")
    return s


def install_id() -> str:
    """Random id created once per installation. Lets a user delete their samples; identifies nobody."""
    s = load_state()
    if not s.get("install_id"):
        s = save_state(install_id=str(uuid.uuid4()))
    return s["install_id"]


def _os() -> str:
    return {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(platform.system(), "linux")


def upload(x: np.ndarray, category: str, timeout: float = 20.0, source: str = "mic") -> str:
    """Send one approved sample. Returns the sample id; raises on any failure."""
    import urllib.request
    if not enabled():
        raise RuntimeError("sample upload is not configured")
    if category not in CATEGORIES:
        raise ValueError(f"unknown category {category}")
    if source not in SOURCES:
        raise ValueError(f"unknown source {source}")
    meta = {"install_id": install_id(), "category": category, "app_version": __version__,
            "os": _os(), "consent": CONSENT, "source": source}
    req = urllib.request.Request(
        SAMPLES_URL.rstrip("/") + "/v1/samples", data=encode_wav(x), method="POST",
        headers={"Content-Type": "audio/wav", "X-NF-Meta": json.dumps(meta),
                 "User-Agent": f"NoiseFilter/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        res = json.loads(r.read(64 * 1024))
    if not res.get("ok"):
        raise RuntimeError(res.get("error", "upload failed"))
    save_state(sent=int(load_state().get("sent", 0)) + 1)
    return res["id"]


def upload_clips(clips: list[np.ndarray], category: str, timeout: float = 20.0) -> int:
    """Send the clips of one audio file (source "file"). Returns how many were sent; raises if none."""
    sent, error = 0, None
    for c in clips:
        try:
            upload(c, category, timeout, source="file")
            sent += 1
        except Exception as e:      # keep going: one refused clip should not lose the others
            error = e
    if not sent and error is not None:
        raise error
    return sent


def delete_my_samples(timeout: float = 20.0) -> int:
    """Ask the service to delete every sample sent from this installation. Returns how many."""
    import urllib.request
    if not enabled():
        raise RuntimeError("sample upload is not configured")
    req = urllib.request.Request(
        f"{SAMPLES_URL.rstrip('/')}/v1/samples?install_id={install_id()}", method="DELETE",
        headers={"User-Agent": f"NoiseFilter/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        res = json.loads(r.read(64 * 1024))
    save_state(sent=0)
    return int(res.get("deleted", 0))
