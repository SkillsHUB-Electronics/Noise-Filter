import os
import time
import numpy as np
from PySide6 import QtCore, QtWidgets as W
from ..core import FRAME_SIZE, FRAME_MS, SAMPLE_RATE
from ..core import native
from .. import model_update
from ..i18n import tr
from . import settings
from .spectrum_plot import SpectrumPlot

LANGS = [("en", "English"), ("id", "Bahasa Indonesia")]
LEARN_SECONDS = 3


def level_bar():
    b = W.QProgressBar()
    b.setRange(-80, 0)
    b.setFormat("%v dB")
    b.setTextVisible(True)
    return b


class _ModelSignal(QtCore.QObject):
    done = QtCore.Signal(object, object)   # (installed model entry | None, error | None), queued to the UI thread


class MainWindow(W.QMainWindow):
    def __init__(self, demo: bool = False):
        super().__init__()
        self.data = settings.load()
        self.lang = self.data.get("lang", "en")
        # C++ nf-core when the library is built (lower latency, ~15x cheaper DSP), else pure Python.
        cfg = settings.pipeline_config(self.data)
        if cfg.denoise == "onnx" and not os.path.isfile(cfg.onnx_model):
            cfg.onnx_model = model_update.current_model_path()   # bundled / latest downloaded model
            if not cfg.onnx_model:
                cfg.denoise = "spectral"
        self.pipe = native.create_pipeline(cfg)
        self.native = getattr(self.pipe, "native", False)
        self.engine = None
        self.native_engine = False
        self.demo = demo
        self._demo_t = 0
        self._rng = np.random.default_rng(1)
        self._build()
        self.retranslate()
        self.refresh_devices()
        self._model_signal = _ModelSignal()
        self._model_signal.done.connect(self._model_update_done)
        if not demo and os.environ.get("NF_NO_UPDATE_CHECK") != "1":
            QtCore.QTimer.singleShot(3000, self._check_model_update)
        self.timer = QtCore.QTimer(self, interval=33)       # ~30 fps UI refresh
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        if demo:
            self.demo_timer = QtCore.QTimer(self, interval=10)
            self.demo_timer.timeout.connect(self._demo_frame)
            self.start_btn.setEnabled(False)
            self.demo_timer.start()

    # ---------- UI construction ----------
    def _build(self):
        c = W.QWidget(); self.setCentralWidget(c)
        root = W.QVBoxLayout(c)

        # devices row
        row = W.QHBoxLayout()
        self.in_lbl, self.out_lbl = W.QLabel(), W.QLabel()
        self.in_cb, self.out_cb = W.QComboBox(), W.QComboBox()
        self.in_cb.setMinimumWidth(240); self.out_cb.setMinimumWidth(240)
        self.refresh_btn = W.QPushButton()
        self.start_btn = W.QPushButton(); self.start_btn.setCheckable(True)
        self.excl = W.QCheckBox()
        self.lang_cb = W.QComboBox()
        for code, name in LANGS: self.lang_cb.addItem(name, code)
        self.lang_cb.setCurrentIndex([c_ for c_, _ in LANGS].index(self.lang))
        for w in (self.in_lbl, self.in_cb, self.out_lbl, self.out_cb, self.refresh_btn, self.excl):
            row.addWidget(w)
        row.addStretch(1); row.addWidget(self.lang_cb); row.addWidget(self.start_btn)
        root.addLayout(row)
        self.refresh_btn.clicked.connect(self.refresh_devices)
        self.start_btn.toggled.connect(self.toggle_engine)
        self.lang_cb.currentIndexChanged.connect(self._lang_changed)

        # analyzers
        plots = W.QHBoxLayout()
        freqs = self.pipe.in_analyzer.freqs
        self.in_plot = SpectrumPlot("", "#e0a030", freqs)
        self.out_plot = SpectrumPlot("", "#30b070", freqs)
        for p, bar_name in ((self.in_plot, "in_bar"), (self.out_plot, "out_bar")):
            col = W.QVBoxLayout(); col.addWidget(p, 1)
            bar = level_bar(); setattr(self, bar_name, bar); col.addWidget(bar)
            plots.addLayout(col)
        root.addLayout(plots, 1)

        # controls
        box = W.QGroupBox(); self.ctrl_box = box
        g = W.QGridLayout(box)
        cfg = self.pipe.cfg
        self.bypass = W.QCheckBox(); self.bypass.setChecked(cfg.bypass)
        self.mode_cb = W.QComboBox()
        self.strength = self._slider(0, 200, int(cfg.strength * 100))
        self.hp = self._slider(0, 300, int(cfg.highpass_hz))
        self.gate_on = W.QCheckBox(); self.gate_on.setChecked(cfg.gate_enabled)
        self.gate_th = self._slider(-90, -20, int(cfg.gate_threshold_db))
        self.gain = self._slider(-20, 20, int(cfg.output_gain_db))
        self.lbls = {k: W.QLabel() for k in ("mode", "strength", "hp", "gate", "gain")}
        self.vals = {k: W.QLabel() for k in ("strength", "hp", "gate", "gain")}
        g.addWidget(self.bypass, 0, 0, 1, 2)
        g.addWidget(self.lbls["mode"], 1, 0); g.addWidget(self.mode_cb, 1, 1, 1, 2)
        for r, (k, s) in enumerate((("strength", self.strength), ("hp", self.hp),
                                    ("gate", self.gate_th), ("gain", self.gain)), start=2):
            g.addWidget(self.lbls[k], r, 0); g.addWidget(s, r, 1); g.addWidget(self.vals[k], r, 2)
        g.addWidget(self.gate_on, 4, 3)
        self.learn_btn, self.train_btn = W.QPushButton(), W.QPushButton()
        self.train_btn.clicked.connect(lambda: self._check_model_update(manual=True))
        g.addWidget(self.learn_btn, 0, 3); g.addWidget(self.train_btn, 1, 3)
        g.setColumnStretch(1, 1)
        root.addWidget(box)

        self.hint = W.QLabel(); self.hint.setWordWrap(True)
        self.status = W.QLabel()
        root.addWidget(self.hint); root.addWidget(self.status)

        self.bypass.toggled.connect(lambda v: self._set(bypass=v))
        self.mode_cb.currentIndexChanged.connect(lambda _: self._mode_changed(self.mode_cb.currentData()))
        self.strength.valueChanged.connect(lambda v: self._set(strength=v / 100))
        self.hp.valueChanged.connect(lambda v: self._set(highpass_hz=float(v)))
        self.gate_on.toggled.connect(lambda v: self._set(gate_enabled=v))
        self.gate_th.valueChanged.connect(lambda v: self._set(gate_threshold_db=float(v)))
        self.gain.valueChanged.connect(lambda v: self._set(output_gain_db=float(v)))
        self.learn_btn.clicked.connect(self.learn_noise)
        self._update_value_labels()

    @staticmethod
    def _slider(lo, hi, val):
        s = W.QSlider(QtCore.Qt.Horizontal); s.setRange(lo, hi); s.setValue(val); return s

    def retranslate(self):
        t = lambda k: tr(k, self.lang)
        self.setWindowTitle(t("app.title"))
        self.in_lbl.setText(t("device.input")); self.out_lbl.setText(t("device.output"))
        self.refresh_btn.setText(t("device.refresh"))
        self.excl.setText(t("device.exclusive"))
        self.start_btn.setText(t("engine.stop") if self.start_btn.isChecked() else t("engine.start"))
        self.in_plot.setTitle(t("analyzer.input")); self.out_plot.setTitle(t("analyzer.output"))
        self.ctrl_box.setTitle(t("controls.title"))
        self.bypass.setText(t("mode.bypass"))
        cur = self.pipe.cfg.denoise
        self.mode_cb.blockSignals(True); self.mode_cb.clear()
        model = model_update.current_model()
        for key in ("off", "spectral", "onnx"):
            label = t(f"denoise.{key}")
            if key == "onnx":
                label = f"{label}  ({model['name']} {model['version']})" if model else f"{label}  ({t('model.missing')})"
            self.mode_cb.addItem(label, key)
        self.mode_cb.setCurrentIndex(["off", "spectral", "onnx"].index(cur))
        self.mode_cb.blockSignals(False)
        for k in self.lbls: self.lbls[k].setText(t(f"label.{k}"))
        self.gate_on.setText(t("label.gate_on"))
        self.learn_btn.setText(t("noise.learn")); self.train_btn.setText(t("model.check"))
        self.hint.setText(t("hint.virtualmic"))

    # ---------- behaviour ----------
    def _set(self, **kw):
        self.pipe.update(**kw)
        self._update_value_labels()
        self._save()

    def _mode_changed(self, mode: str):
        if mode == "onnx":
            path = model_update.current_model_path()
            if not path:
                self.status.setText(tr("model.none", self.lang))
                self.mode_cb.blockSignals(True)
                self.mode_cb.setCurrentIndex(["off", "spectral", "onnx"].index(self.pipe.cfg.denoise))
                self.mode_cb.blockSignals(False)
                return
            try:
                self._set(denoise="onnx", onnx_model=path)
            except Exception as e:      # e.g. engine built without ONNX Runtime
                self.pipe.update(denoise="spectral")
                self.mode_cb.blockSignals(True); self.mode_cb.setCurrentIndex(1); self.mode_cb.blockSignals(False)
                self.status.setText(f"{tr('model.error', self.lang)}: {e}")
            return
        self._set(denoise=mode)

    def _check_model_update(self, manual: bool = False):
        """Background check; a newer verified model is swapped in live. The automatic check at
        start-up stays quiet; a check from the button always reports what happened."""
        self._manual_check = manual
        if manual:
            self.train_btn.setEnabled(False)
            self.status.setText(tr("model.checking", self.lang))
        model_update.update_in_background(lambda entry, err: self._model_signal.done.emit(entry, err))

    def _model_update_done(self, entry, err):
        manual, self._manual_check = getattr(self, "_manual_check", False), False
        self.train_btn.setEnabled(True)
        if entry is None:
            if manual:                   # automatic check: keep quiet when up to date or offline
                cur = model_update.current_model()
                if err is not None:
                    self.status.setText(f"{tr('model.check_failed', self.lang)}: {err}")
                else:
                    self.status.setText(tr("model.latest", self.lang).format(
                        v=cur["version"] if cur else tr("model.missing", self.lang)))
            return
        self.retranslate()
        if self.pipe.cfg.denoise == "onnx":
            self._set(onnx_model=str(entry["path"]))
        self.status.setText(tr("model.updated", self.lang).format(v=entry["version"]))

    def _update_value_labels(self):
        c = self.pipe.cfg
        self.vals["strength"].setText(f"{c.strength:.2f}")
        self.vals["hp"].setText("off" if c.highpass_hz <= 0 else f"{c.highpass_hz:.0f} Hz")
        self.vals["gate"].setText(f"{c.gate_threshold_db:.0f} dB")
        self.vals["gain"].setText(f"{c.output_gain_db:+.0f} dB")

    def _save(self):
        self.data["pipeline"] = self.pipe.cfg.to_dict()
        self.data["lang"] = self.lang
        self.data["in_dev"] = self.in_cb.currentData()
        self.data["out_dev"] = self.out_cb.currentData()
        try: settings.save(self.data)
        except OSError: pass

    def _lang_changed(self, _):
        self.lang = self.lang_cb.currentData(); self.retranslate(); self._save()

    def refresh_devices(self):
        self.in_cb.clear(); self.out_cb.clear()
        ins = outs = None
        if self.native:                              # WASAPI enumeration inside nf-core (Windows)
            ins, outs = native.list_devices("input"), native.list_devices("output")
            if ins or outs:
                for d in ins: self.in_cb.addItem(d.name + ("  *" if d.is_default else ""), d.id)
                for d in outs: self.out_cb.addItem(d.name + ("  *" if d.is_default else ""), d.id)
        if not (ins or outs):
            self.native_engine = False
            try:
                from ..audio import devices
                devices.refresh()
                ins, outs = devices.list_devices("input"), devices.list_devices("output")
            except Exception as e:                  # no sounddevice / no audio backend
                self.status.setText(f"Audio unavailable: {e}")
                return
            for d in ins: self.in_cb.addItem(d.name + ("  *" if d.is_default else ""), d.index)
            for d in outs: self.out_cb.addItem(d.name + ("  *" if d.is_default else ""), d.index)
        else:
            self.native_engine = True
        # prefer saved choice; else prefer a VB-Cable input for output
        for cb, key in ((self.in_cb, "in_dev"), (self.out_cb, "out_dev")):
            i = cb.findData(self.data.get(key)); 
            if i >= 0: cb.setCurrentIndex(i)
        if self.data.get("out_dev") is None:
            for i in range(self.out_cb.count()):
                if "cable input" in self.out_cb.itemText(i).lower(): self.out_cb.setCurrentIndex(i); break

    def toggle_engine(self, on: bool):
        t = lambda k: tr(k, self.lang)
        if on:
            try:
                if self.native_engine:
                    self.engine = native.NativeEngine(self.pipe, self.in_cb.currentData(),
                                                      self.out_cb.currentData(), exclusive=self.excl.isChecked())
                else:
                    from ..audio.engine import Engine
                    self.engine = Engine(self.pipe, self.in_cb.currentData(), self.out_cb.currentData(),
                                         exclusive=self.excl.isChecked())
                self.engine.start()
            except Exception as e:
                self.start_btn.blockSignals(True); self.start_btn.setChecked(False); self.start_btn.blockSignals(False)
                self.status.setText(f"{t('engine.error')}: {e}")
                on = False
        else:
            if self.engine: self.engine.stop(); self.engine = None
        for w in (self.in_cb, self.out_cb, self.refresh_btn, self.excl): w.setEnabled(not on)
        self.start_btn.setText(t("engine.stop") if on else t("engine.start"))
        self._save()

    def learn_noise(self):
        sp = self.pipe.spectral
        sp.start_learning()
        self.learn_btn.setEnabled(False)
        self.learn_btn.setText(tr("noise.learning", self.lang).format(s=LEARN_SECONDS))
        QtCore.QTimer.singleShot(LEARN_SECONDS * 1000, self._finish_learn)

    def _finish_learn(self):
        self.pipe.spectral.finish_learning()
        self.learn_btn.setEnabled(True); self.retranslate()
        self.status.setText(tr("noise.learned", self.lang))

    def _demo_frame(self):
        """No audio device (e.g. headless): feed a synthetic 'voice + noise' signal."""
        t = (self._demo_t + np.arange(FRAME_SIZE)) / SAMPLE_RATE
        self._demo_t += FRAME_SIZE
        voice = 0.25 * (np.sin(2 * np.pi * 220 * t) + 0.5 * np.sin(2 * np.pi * 880 * t)
                        + 0.3 * np.sin(2 * np.pi * 2600 * t)) * (0.5 + 0.5 * np.sin(2 * np.pi * 1.5 * t))
        noise = 0.03 * self._rng.standard_normal(FRAME_SIZE) + 0.02 * np.sin(2 * np.pi * 50 * t)
        t0 = time.perf_counter()
        self.pipe.process((voice + noise).astype(np.float32))
        self._cost = 0.9 * getattr(self, "_cost", 0) + 0.1 * (time.perf_counter() - t0) * 1000

    def _tick(self):
        p = self.pipe
        i_db, o_db = p.in_analyzer.spectrum_db(), p.out_analyzer.spectrum_db()
        self.in_plot.set_data(i_db)
        self.out_plot.set_data(o_db, ref=i_db)
        self.in_bar.setValue(int(max(-80, p.in_analyzer.level_db())))
        self.out_bar.setValue(int(max(-80, p.out_analyzer.level_db())))
        backend = tr("engine.backend", self.lang).format(name="C++" if self.native else "Python")
        if self.engine and hasattr(self.engine, "stats"):
            s = self.engine.stats()
            self.status.setText(f"{backend}   xruns: {s['xruns']}   DSP: {s['dsp_avg_us'] / 1000:.2f} ms "
                                f"(max {s['dsp_max_us'] / 1000:.2f}) / {FRAME_MS:.0f} ms   "
                                f"{tr('engine.latency', self.lang)}: ~{s['latency_ms']:.0f} ms")
        elif self.engine:
            self.status.setText(f"{backend}   xruns: {self.engine.xruns}   DSP: {FRAME_MS:.0f} ms frames @ {SAMPLE_RATE // 1000} kHz")
        elif self.demo:
            self.status.setText(f"{backend}   DEMO signal   DSP cost: {getattr(self, '_cost', 0):.2f} ms / {FRAME_MS:.0f} ms frame")

    def closeEvent(self, e):
        if self.engine: self.engine.stop()
        self._save(); super().closeEvent(e)
