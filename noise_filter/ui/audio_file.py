"""Decode compressed audio files (MP3, M4A, FLAC, OGG...) with Qt Multimedia.

WAV files are decoded by noise_filter.contribute without Qt. Qt's FFmpeg / Media Foundation
backend handles the rest, so the installer needs no extra codec library.
"""
from __future__ import annotations

import numpy as np

from ..contribute import AudioFileError

FILTER = "*.wav *.mp3 *.m4a *.aac *.flac *.ogg *.opus *.wma"


def qt_decode(path: str, timeout_s: float = 120.0) -> tuple[np.ndarray, int]:
    """Decode `path` to (mono float32, sample rate). Runs a local event loop until done."""
    try:
        from PySide6 import QtCore
        from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat
    except Exception as e:  # QtMultimedia missing in this build
        raise AudioFileError("unsupported") from e

    dec = QAudioDecoder()
    fmt = QAudioFormat()
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
    fmt.setChannelCount(1)
    fmt.setSampleRate(48000)
    dec.setAudioFormat(fmt)          # the backend converts when it can; we check what we got
    parts, rate, failed = [], [0], [False]
    loop = QtCore.QEventLoop()

    def on_buffer():
        while dec.bufferAvailable():
            buf = dec.read()
            f = buf.format()
            ch = max(1, f.channelCount())
            raw = bytes(buf.constData()[:buf.byteCount()]) if hasattr(buf, "byteCount") else bytes(buf.data())
            sf = f.sampleFormat()
            if sf == QAudioFormat.SampleFormat.Float:
                x = np.frombuffer(raw, "<f4")
            elif sf == QAudioFormat.SampleFormat.Int16:
                x = np.frombuffer(raw, "<i2").astype(np.float32) / 32768
            elif sf == QAudioFormat.SampleFormat.Int32:
                x = (np.frombuffer(raw, "<i4").astype(np.float64) / 2 ** 31).astype(np.float32)
            elif sf == QAudioFormat.SampleFormat.UInt8:
                x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128
            else:
                continue
            parts.append(x[:len(x) // ch * ch].reshape(-1, ch).mean(1))
            rate[0] = f.sampleRate()

    def on_error(*_):
        failed[0] = True
        loop.quit()

    dec.bufferReady.connect(on_buffer)
    dec.finished.connect(loop.quit)
    dec.error.connect(on_error)
    QtCore.QTimer.singleShot(int(timeout_s * 1000), loop.quit)
    dec.setSource(QtCore.QUrl.fromLocalFile(path))
    dec.start()
    loop.exec()
    on_buffer()
    dec.stop()
    if failed[0] and not parts:
        raise AudioFileError("unsupported")
    if not parts or not rate[0]:
        raise AudioFileError("empty")
    return np.concatenate(parts).astype(np.float32), rate[0]
