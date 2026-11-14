"""Before/after comparison for Vocal mode and the Mix control on a synthetic sung phrase.

    python tools/vocal_compare.py [out_dir]

Writes WAV files (clean, noisy, each setting) and a spectrogram/harmonic chart, and prints:
harmonic retention (energy kept on the first 24 harmonics vs the clean voice, dB), the level of
the upper harmonics (> 3 kHz), the noise left in pauses, and SI-SDR. Synthetic voice:
vibrato, 24 harmonics, held notes with natural decay, breath noise; fan-like noise at 15 dB SNR, learned first like 'Learn noise'.
"""
import sys
import wave
from pathlib import Path

import numpy as np

from noise_filter.core import Pipeline, PipelineConfig, FRAME_SIZE, SAMPLE_RATE

SR = SAMPLE_RATE
NOTES = [(0.2, 2.6, 220.0), (3.0, 4.2, 246.9), (4.4, 7.4, 293.7)]   # start, end (s), f0 (Hz): held notes


def voice(secs=9.0, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(int(SR * secs)) / SR
    y = np.zeros_like(t)
    f0_track = np.zeros_like(t)
    for a, b, f0 in NOTES:
        m = (t >= a) & (t < b + 0.6)
        tt = t[m] - a
        env = np.minimum(tt / 0.08, 1.0) * np.where(t[m] < b, 1.0, np.exp(-(t[m] - b) / 0.15))
        f = f0 * (1 + 0.018 * np.sin(2 * np.pi * 5.5 * tt) * np.minimum(tt / 0.6, 1))
        ph = 2 * np.pi * np.cumsum(f) / SR
        for h in range(1, 25):
            if h * f0 * 1.03 > SR / 2:
                break
            amp = (1 / h ** 1.4) * (1.6 if 2 <= h * f0 / 1000 <= 3.5 else 1.0)   # singer's formant
            y[m] += amp * np.sin(h * ph) * env
        f0_track[m] = np.where(t[m] < b, f, f0_track[m])
        breath = rng.standard_normal(m.sum()) * 0.012 * env
        y[m] += np.convolve(breath, np.ones(8) / 8, "same")
    return (0.2 * y / np.max(np.abs(y))).astype(np.float32), f0_track


def noise(n, seed=2):
    rng = np.random.default_rng(seed)
    w = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    w /= np.maximum(f, 50) ** 0.5                       # pink-ish fan noise
    x = np.fft.irfft(w, n)
    t = np.arange(n) / SR
    x = x / np.std(x) + 0.3 * np.sin(2 * np.pi * 120 * t)
    return x.astype(np.float32)


def run(cfg, x, learn):
    """Like the app after 'Learn noise': learn the room noise first, then filter."""
    p = Pipeline(cfg)
    p.spectral.start_learning()
    for i in range(0, len(learn) - FRAME_SIZE + 1, FRAME_SIZE):
        p.process(learn[i:i + FRAME_SIZE])
    p.spectral.finish_learning()
    out = np.concatenate([p.process(x[i:i + FRAME_SIZE]) for i in range(0, len(x) - FRAME_SIZE + 1, FRAME_SIZE)])
    return out[FRAME_SIZE:]           # remove the 1-frame denoiser delay


def harmonic_kept(sig, clean, f0_track, fmin=0.0, fmax=SR / 2):
    """How much of the clean voice's harmonics survives, in dB (0 = all of it).

    Per STFT frame and harmonic, the output is projected onto the clean voice (complex
    correlation over the harmonic's bins), so the remaining noise, which is uncorrelated,
    does not count as "kept harmonic"."""
    n, hop = 2048, 512
    win = np.hanning(n)
    num = den = 0.0
    for s in range(0, min(len(sig), len(clean)) - n, hop):
        f0 = f0_track[s + n // 2]
        if f0 <= 0:
            continue
        Y = np.fft.rfft(sig[s:s + n] * win)
        S = np.fft.rfft(clean[s:s + n] * win)
        for h in range(1, 25):
            fh = h * f0
            if fh < fmin or fh > min(fmax, SR / 2 - 200):
                continue
            k = int(round(fh * n / SR))
            num += np.real(np.sum(Y[k - 2:k + 3] * np.conj(S[k - 2:k + 3])))
            den += np.sum(np.abs(S[k - 2:k + 3]) ** 2)
    return 20 * np.log10(max(num / den, 1e-6))


def si_sdr(ref, est):
    a = np.dot(est, ref) / (np.dot(ref, ref) + 1e-12)
    e = est - a * ref
    return 10 * np.log10(np.sum((a * ref) ** 2) / (np.sum(e ** 2) + 1e-12))


def save_wav(path, x):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


SETTINGS = [
    ("standard", "Standard (strength 1.0)", dict()),
    ("standard-0.7", "Standard, strength 0.7", dict(strength=0.7)),
    ("vocal", "Vocal mode", dict(vocal_mode=True)),
    ("vocal-mix80", "Vocal mode + Mix 80 %", dict(vocal_mode=True, mix=0.8)),
]


def main(out_dir="vocal-compare"):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    clean, f0 = voice()
    nz_all = noise(len(clean) + 2 * SR)
    nz_all *= np.sqrt(np.mean(clean ** 2) / np.mean(nz_all ** 2)) / 10 ** (15 / 20)    # 15 dB SNR
    learn, nz = nz_all[:2 * SR], nz_all[2 * SR:]
    noisy = (clean + nz).astype(np.float32)
    base = dict(highpass_hz=80.0, gate_enabled=True, limiter_enabled=False)
    pause = np.zeros(len(clean), bool); pause[int(8.3 * SR):] = True     # 0.7 s of room noise only
    noise_in = 10 * np.log10(np.mean(noisy[pause] ** 2))
    save_wav(out / "0-clean.wav", clean); save_wav(out / "1-noisy.wav", noisy)
    ref = run(PipelineConfig(denoise="off", highpass_hz=80.0, gate_enabled=False, limiter_enabled=False),
              np.concatenate([clean, np.zeros(FRAME_SIZE, np.float32)]), np.zeros(0, np.float32))
    ref = np.concatenate([np.zeros(FRAME_SIZE, np.float32), ref])[:len(clean)]   # same high-pass, no denoiser delay
    rows, outs = [], {}
    for i, (key, label, kw) in enumerate(SETTINGS):
        y = run(PipelineConfig(**base, **kw), noisy, learn)
        n = min(len(y), len(clean))
        c, yy, pz, ff = ref[:n], y[:n], pause[:n], f0[:n]
        outs[key] = yy
        save_wav(out / f"{i + 2}-{key}.wav", yy)
        rows.append((label, harmonic_kept(yy, c, ff), harmonic_kept(yy, c, ff, fmin=3000),
                     10 * np.log10(np.mean(yy[pz] ** 2) + 1e-12) - noise_in, si_sdr(c, yy)))
    print(f"{'setting':28s} {'harmonics':>10s} {'harm >3k':>9s} {'pause noise':>12s} {'SI-SDR':>7s}")
    for r in rows:
        print(f"{r[0]:28s} {r[1]:+9.1f}dB {r[2]:+8.1f}dB {r[3]:+11.1f}dB {r[4]:6.1f}dB")
    held, held_sigs = held_note()
    for key, sig in held_sigs.items():
        save_wav(out / f"held-note-{key}.wav", sig)
    print("\nOne 11 s held note, no learned profile (adaptive noise estimate): upper harmonics (> 3 kHz) kept")
    for label, early, late in held:
        print(f"{label:28s} 1-3 s: {early:+5.1f} dB   8-11 s: {late:+5.1f} dB")
    try:
        chart(out, held_sigs, rows, held)
    except ImportError:
        print("matplotlib not installed: no chart")
    return rows


def held_note():
    """Adaptive mode slowly learns a long sung note as 'noise'; Vocal mode should not."""
    global NOTES
    saved, NOTES = NOTES, [(0.5, 11.5, 196.0)]
    try:
        clean, f0 = voice(12.0)
    finally:
        NOTES = saved
    nz = noise(len(clean))
    nz *= np.sqrt(np.mean(clean ** 2) / np.mean(nz ** 2)) / 10 ** (15 / 20)
    x = (clean + nz).astype(np.float32)
    res, sigs = [], {"clean": clean, "noisy": x}
    for key, label, kw in SETTINGS[:1] + SETTINGS[2:3]:
        y = run(PipelineConfig(highpass_hz=0.0, limiter_enabled=False, **kw), x, np.zeros(0, np.float32))
        k = [harmonic_kept(y[a * SR:b * SR], clean[a * SR:b * SR], f0[a * SR:b * SR], fmin=3000) for a, b in ((1, 3), (8, 11))]
        res.append((label, *k))
        sigs[key] = y
    return res, sigs


def chart(out, hs, rows, held):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 3, figsize=(15, 7.8), constrained_layout=True)
    fig.suptitle("Noise Filter: Vocal mode on a sung note (synthetic voice, fan noise)", fontsize=13)
    for a, (title, key) in zip(ax[0], [("Noisy input", "noisy"), ("Standard filter (strength 1.0)", "standard"),
                                       ("Vocal mode", "vocal")]):
        a.specgram(hs[key], NFFT=2048, Fs=SR, noverlap=1536, cmap="magma", vmin=-150, vmax=-40)
        a.set_ylim(0, 8000); a.set_title(title + ": 11 s held note"); a.set_xlabel("time (s)"); a.set_ylabel("Hz")
    a = ax[1, 0]
    n, s0 = 16384, int(9.0 * SR)
    win = np.hanning(n); fr = np.fft.rfftfreq(n, 1 / SR)
    for key, title, col in (("clean", "Clean voice", "#777"), ("standard", "Standard filter", "#e07b00"),
                            ("vocal", "Vocal mode", "#1f9e6e")):
        sig = hs[key] if key == "clean" else np.concatenate([hs[key][FRAME_SIZE:], np.zeros(FRAME_SIZE)])
        sp = 20 * np.log10(np.abs(np.fft.rfft(sig[s0:s0 + n] * win)) + 1e-9)
        a.plot(fr, sp, lw=0.9, color=col, label=title)
    a.set_xlim(2500, 6500); a.set_ylim(-40, 50); a.set_title("Upper harmonics after 9 s of the note")
    a.set_xlabel("Hz"); a.set_ylabel("dB"); a.legend(fontsize=8, loc="upper right")
    a = ax[1, 1]
    labels = [h[0] for h in held]
    yv = np.arange(len(held))
    a.barh(yv - 0.2, [h[1] for h in held], 0.4, label="1-3 s", color="#9cc")
    a.barh(yv + 0.2, [h[2] for h in held], 0.4, label="8-11 s", color="#1f9e6e")
    a.set_yticks(yv, labels); a.invert_yaxis(); a.axvline(0, color="k", lw=0.8)
    a.set_xlabel("dB vs clean voice (0 = fully kept)"); a.set_title("Held note: harmonics > 3 kHz kept")
    a.legend(fontsize=8)
    a = ax[1, 2]
    yv = np.arange(len(rows))
    a.barh(yv - 0.2, [r[2] for r in rows], 0.4, label="harmonics > 3 kHz kept (dB)", color="#1f9e6e")
    a.barh(yv + 0.2, [r[3] for r in rows], 0.4, label="noise in pauses (dB)", color="#567")
    a.set_yticks(yv, [r[0] for r in rows]); a.invert_yaxis(); a.axvline(0, color="k", lw=0.8)
    a.set_title("Phrase after 'Learn noise': harmonics vs noise")
    a.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=2)
    a.set_xlabel("dB (0 = unchanged)")
    fig.savefig(out / "vocal-compare.png", dpi=110)


if __name__ == "__main__":
    main(*sys.argv[1:])
