"""Realtime engine: input device -> Pipeline -> output device (e.g. VB-Cable).

Uses two callback streams (input and output can be different devices) joined by a
tiny lock-free-ish ring buffer. Keep the target fill at ~1 frame for low latency.
"""
import threading
import numpy as np
from ..core import Pipeline, FRAME_SIZE, SAMPLE_RATE


class Ring:
    def __init__(self, cap=FRAME_SIZE * 16):
        self.buf = np.zeros(cap, np.float32)
        self.cap, self.r, self.w, self.lock = cap, 0, 0, threading.Lock()

    def available(self): return self.w - self.r

    def write(self, x):
        with self.lock:
            for s in (x,):
                idx = (self.w + np.arange(len(s))) % self.cap
                self.buf[idx] = s
                self.w += len(s)
            if self.w - self.r > self.cap:       # overflow: drop oldest
                self.r = self.w - self.cap

    def read(self, n):
        with self.lock:
            if self.w - self.r < n:
                return None
            idx = (self.r + np.arange(n)) % self.cap
            self.r += n
            return self.buf[idx].copy()


class Engine:
    def __init__(self, pipeline: Pipeline, in_dev: int, out_dev: int, exclusive: bool = False):
        import sounddevice as sd
        self.sd, self.pipe = sd, pipeline
        self.inring, self.outring = Ring(), Ring()
        extra = sd.WasapiSettings(exclusive=exclusive) if exclusive else None
        kw = dict(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                  blocksize=FRAME_SIZE, latency="low", extra_settings=extra)
        self.stream_in = sd.InputStream(device=in_dev, callback=self._in_cb, **kw)
        self.stream_out = sd.OutputStream(device=out_dev, callback=self._out_cb, **kw)
        self.xruns = 0

    def _in_cb(self, indata, frames, t, status):
        if status: self.xruns += 1
        self.inring.write(indata[:, 0])
        while (f := self.inring.read(FRAME_SIZE)) is not None:
            self.outring.write(self.pipe.process(f))

    def _out_cb(self, outdata, frames, t, status):
        if status: self.xruns += 1
        f = self.outring.read(frames)
        outdata[:, 0] = f if f is not None else 0.0

    def start(self): self.stream_in.start(); self.stream_out.start()

    def stop(self):
        self.stream_in.stop(); self.stream_out.stop()
        self.stream_in.close(); self.stream_out.close()
