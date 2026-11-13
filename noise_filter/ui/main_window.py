import os
import time
import numpy as np
from PySide6 import QtCore, QtWidgets as W
from ..core import FRAME_SIZE, FRAME_MS, SAMPLE_RATE
from ..core import native
from .. import contribute, model_update
from ..i18n import tr
from . import autostart, settings
from .spectrum_plot import SpectrumPlot
from .eq_panel import EqPanel
from .dynamics_panel import DynamicsPanel
from .contribute_dialog import ContributeDialog, UploadWorker

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


class _SampleSignal(QtCore.QObject):
    ready = QtCore.Signal(object)          # screened 'Learn noise' recording (np.ndarray) or None


def _with_dot(icon, QtGui):
    """Tray icon while the filter runs: the logo with a green dot in the corner."""
    out = QtGui.QIcon()
    for s in (16, 20, 24, 32, 48, 64):
        pix = icon.pixmap(s, s)
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = max(5, s * 0.45)
        p.setPen(QtGui.QPen(QtGui.QColor("white"), max(1.0, s / 16)))
        p.setBrush(QtGui.QColor("#22c55e"))
        p.drawEllipse(QtCore.QRectF(s - r - 0.5, s - r - 0.5, r, r))
        p.end()
        out.addPixmap(pix)
    return out


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
        self._quitting = False
        self._shut_down = False
        self._build()
        self._build_tray()
        self.retranslate()
        self.refresh_devices()
        geo = self.data.get("geometry")
        if not (geo and self.restoreGeometry(QtCore.QByteArray.fromBase64(geo.encode("ascii")))):
            self.resize(1100, 720)
        app = W.QApplication.instance()
        app.aboutToQuit.connect(self._shutdown)
        app.commitDataRequest.connect(lambda _: setattr(self, "_quitting", True))   # Windows sign-out / shutdown
        autostart.refresh()
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
        elif self.data.get("running") and self.resume_cb.isChecked():
            QtCore.QTimer.singleShot(300, lambda: self.start_btn.setChecked(True))   # it was on last time

    # ---------- UI construction ----------
    def _build(self):
        c = W.QWidget(); self.setCentralWidget(c)
        root = W.QVBoxLayout(c)

        # devices: label | combo | extra, two rows; the big Start button on the right
        self.dev_box = W.QGroupBox()
        d = W.QGridLayout(self.dev_box)
        self.in_lbl, self.out_lbl = W.QLabel(), W.QLabel()
        self.in_cb, self.out_cb = W.QComboBox(), W.QComboBox()
        for cb in (self.in_cb, self.out_cb):     # long device names must not widen the window
            cb.setSizeAdjustPolicy(W.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            cb.setMinimumContentsLength(18)
            cb.setSizePolicy(W.QSizePolicy.Expanding, W.QSizePolicy.Fixed)
        self.refresh_btn = W.QPushButton()
        self.excl = W.QCheckBox(); self.excl.setChecked(bool(self.data.get("exclusive", False)))
        self.excl.toggled.connect(lambda _: self._save())
        self.start_btn = W.QPushButton(); self.start_btn.setCheckable(True)
        self.start_btn.setMinimumWidth(130)
        self.start_btn.setSizePolicy(W.QSizePolicy.Preferred, W.QSizePolicy.Expanding)
        f = self.start_btn.font(); f.setBold(True); f.setPointSizeF(f.pointSizeF() * 1.2)
        self.start_btn.setFont(f)
        d.addWidget(self.in_lbl, 0, 0); d.addWidget(self.in_cb, 0, 1); d.addWidget(self.refresh_btn, 0, 2)
        d.addWidget(self.out_lbl, 1, 0); d.addWidget(self.out_cb, 1, 1); d.addWidget(self.excl, 1, 2)
        d.addWidget(self.start_btn, 0, 3, 2, 1)
        d.setColumnStretch(1, 1)
        root.addWidget(self.dev_box)
        self.refresh_btn.clicked.connect(self.refresh_devices)
        self.start_btn.toggled.connect(self.toggle_engine)

        # analyzers and equalizer share the middle as tabs
        self.tabs = W.QTabWidget()
        # every tab owns its controls: spectra + filter, EQ, dynamics, settings
        spec_tab = W.QWidget()
        self._spec_lay = W.QVBoxLayout(spec_tab)
        self._spec_lay.setContentsMargins(4, 4, 4, 4)
        plots = W.QHBoxLayout()
        self._spec_lay.addLayout(plots, 1)
        freqs = self.pipe.in_analyzer.freqs
        self.in_plot = SpectrumPlot("", "#e0a030", freqs)
        self.out_plot = SpectrumPlot("", "#30b070", freqs)
        for p, bar_name in ((self.in_plot, "in_bar"), (self.out_plot, "out_bar")):
            p.setMinimumHeight(160)
            col = W.QVBoxLayout(); col.addWidget(p, 1)
            bar = level_bar(); setattr(self, bar_name, bar); col.addWidget(bar)
            plots.addLayout(col)
        self.tabs.addTab(spec_tab, "")
        cfg0 = self.pipe.cfg
        self.eq_panel = EqPanel(freqs, cfg0.eq_enabled, cfg0.eq_bands, self.data.get("eq_presets", {}), self.lang)
        self.eq_panel.layout().setContentsMargins(4, 4, 4, 4)
        self.eq_panel.changed.connect(lambda on, bands: self._set(eq_enabled=on, eq_bands=bands))
        self.eq_panel.presets_changed.connect(self._eq_presets_changed)
        self.tabs.addTab(self.eq_panel, "")
        self.dyn_panel = DynamicsPanel(self.pipe.cfg, self.lang)
        self.dyn_panel.changed.connect(lambda kw: self._set(**kw))
        self.tabs.addTab(self.dyn_panel, "")
        root.addWidget(self.tabs, 1)

        # filter controls: label | slider | value, one row each
        box = W.QGroupBox(); self.ctrl_box = box
        g = W.QGridLayout(box)
        cfg = self.pipe.cfg
        self.bypass = W.QCheckBox(); self.bypass.setChecked(cfg.bypass)
        self.mode_cb = W.QComboBox()
        self.mode_cb.setSizeAdjustPolicy(W.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.mode_cb.setMinimumContentsLength(16)
        self.strength = self._slider(0, 200, int(cfg.strength * 100))
        self.hp = self._slider(0, 300, int(cfg.highpass_hz))
        self.gate_on = W.QCheckBox(); self.gate_on.setChecked(cfg.gate_enabled)   # doubles as the row label
        self.gate_th = self._slider(-90, -20, int(cfg.gate_threshold_db))
        self.gain = self._slider(-20, 20, int(cfg.output_gain_db))
        self.lbls = {k: W.QLabel() for k in ("mode", "strength", "hp", "gain")}
        self.vals = {k: W.QLabel() for k in ("strength", "hp", "gate", "gain")}
        val_w = self.fontMetrics().horizontalAdvance("-100 dB") + 8
        for v in self.vals.values():
            v.setMinimumWidth(val_w); v.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.learn_btn, self.train_btn = W.QPushButton(), W.QPushButton()
        self.train_btn.clicked.connect(lambda: self._check_model_update(manual=True))
        # one column: label | control | value, every slider the same width, in signal-chain order
        top = W.QHBoxLayout(); top.addWidget(self.bypass); top.addStretch(1); top.addWidget(self.learn_btn)
        g.addLayout(top, 0, 0, 1, 3)
        g.addWidget(self.lbls["mode"], 1, 0); g.addWidget(self.mode_cb, 1, 1, 1, 2)
        for r, (lbl, sl_, k) in enumerate(((self.lbls["strength"], self.strength, "strength"),
                                           (self.lbls["hp"], self.hp, "hp"),
                                           (self.gate_on, self.gate_th, "gate"),
                                           (self.lbls["gain"], self.gain, "gain")), start=2):
            g.addWidget(lbl, r, 0); g.addWidget(sl_, r, 1); g.addWidget(self.vals[k], r, 2)
        g.setColumnStretch(1, 1)
        g.setVerticalSpacing(4)
        self._spec_lay.addWidget(box)

        # F3: offer to send the 'Learn noise' recording (only when the intake service is configured)
        self.contrib_cb, self.contrib_del = W.QCheckBox(), W.QPushButton()
        self.contrib_cb.setChecked(contribute.load_state().get("ask", True))
        self.contrib_cb.toggled.connect(lambda v: contribute.save_state(ask=v))
        self.contrib_del.clicked.connect(self._delete_samples)
        self._sample_signal = _SampleSignal()
        self._sample_signal.ready.connect(self._offer_sample)
        self._uploader = UploadWorker()
        self._uploader.done.connect(self._upload_done)
        self._capturing = False

        # Settings tab: language; background & startup; AI model & noise samples
        self.lang_lbl = W.QLabel()
        self.lang_cb = W.QComboBox()
        for code, name in LANGS: self.lang_cb.addItem(name, code)
        self.lang_cb.setCurrentIndex([c_ for c_, _ in LANGS].index(self.lang))
        self.lang_cb.currentIndexChanged.connect(self._lang_changed)
        self.tray_cb = W.QCheckBox(); self.tray_cb.setChecked(bool(self.data.get("close_to_tray", True)))
        self.tray_cb.setEnabled(W.QSystemTrayIcon.isSystemTrayAvailable())
        self.autostart_cb = W.QCheckBox(); self.autostart_cb.setChecked(autostart.is_enabled())
        self.autostart_cb.setEnabled(autostart.supported())
        self.resume_cb = W.QCheckBox(); self.resume_cb.setChecked(bool(self.data.get("resume", True)))
        page = W.QWidget()
        pl = W.QVBoxLayout(page)
        self.gen_box, self.bg_box, self.ai_box = W.QGroupBox(), W.QGroupBox(), W.QGroupBox()
        gl = W.QHBoxLayout(self.gen_box)
        self.lang_cb.setMinimumWidth(200)
        gl.addWidget(self.lang_lbl); gl.addWidget(self.lang_cb); gl.addStretch(1)
        bl = W.QVBoxLayout(self.bg_box)
        self.set_notes = {}
        for w in (self.tray_cb, self.autostart_cb, self.resume_cb):
            note = W.QLabel(); note.setWordWrap(True)
            note.setStyleSheet("color: palette(placeholder-text); margin-left: 24px; margin-bottom: 4px;")
            bl.addWidget(w); bl.addWidget(note)
            self.set_notes[w] = note
        al = W.QVBoxLayout(self.ai_box)
        row = W.QHBoxLayout(); row.addWidget(self.train_btn); row.addStretch(1)
        al.addLayout(row)
        al.addWidget(self.contrib_cb)
        row = W.QHBoxLayout(); row.addWidget(self.contrib_del); row.addStretch(1)
        al.addLayout(row)
        # one column of equally wide boxes, in order of how often they are needed
        for b in (self.gen_box, self.bg_box, self.ai_box):
            b.setMaximumWidth(760)
            pl.addWidget(b)
        pl.addStretch(1)
        self.set_box = page
        self.tabs.addTab(self.set_box, "")
        self.tabs.setCurrentIndex(int(self.data.get("tab", 0)) % self.tabs.count())
        self.tabs.currentChanged.connect(lambda _: self._save())
        self.tray_cb.toggled.connect(lambda _: self._save())
        self.resume_cb.toggled.connect(lambda _: self._save())
        self.autostart_cb.toggled.connect(self._autostart_changed)

        self.hint = W.QLabel(); self.hint.setWordWrap(True)
        root.addWidget(self.hint)
        self.status = W.QLabel()   # long stats must never force the window wider
        self.status.setSizePolicy(W.QSizePolicy.Ignored, W.QSizePolicy.Preferred)
        self.statusBar().addWidget(self.status, 1)

        self.bypass.toggled.connect(lambda v: self._set(bypass=v))
        self.mode_cb.currentIndexChanged.connect(lambda _: self._mode_changed(self.mode_cb.currentData()))
        self.strength.valueChanged.connect(lambda v: self._set(strength=v / 100))
        self.hp.valueChanged.connect(lambda v: self._set(highpass_hz=float(v)))
        self.gate_on.toggled.connect(lambda v: self._set(gate_enabled=v))
        self.gate_th.valueChanged.connect(lambda v: self._set(gate_threshold_db=float(v)))
        self.gain.valueChanged.connect(lambda v: self._set(output_gain_db=float(v)))
        self.learn_btn.clicked.connect(self.learn_noise)
        self._update_value_labels()

    def _build_tray(self):
        from .app import app_icon
        from PySide6 import QtGui
        self._icon = app_icon(QtGui)
        self._icon_on = _with_dot(self._icon, QtGui)
        self.tray = W.QSystemTrayIcon(self._icon, self)
        m = W.QMenu(self)
        self.act_show = m.addAction("", self.toggle_window)
        self.act_run = m.addAction(""); self.act_run.setCheckable(True)
        self.act_run.toggled.connect(self.start_btn.setChecked)
        m.addSeparator()
        self.act_quit = m.addAction("", self.quit_app)
        m.aboutToShow.connect(self._update_tray)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(
            lambda r: self.toggle_window() if r in (W.QSystemTrayIcon.Trigger, W.QSystemTrayIcon.DoubleClick) else None)
        if W.QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _update_tray(self):
        t = lambda k: tr(k, self.lang)
        on = self.engine is not None
        self.act_show.setText(t("tray.hide") if self.isVisible() else t("tray.show"))
        self.act_run.blockSignals(True); self.act_run.setChecked(on); self.act_run.blockSignals(False)
        self.act_run.setText(t("tray.filter")); self.act_quit.setText(t("tray.quit"))
        self.tray.setIcon(self._icon_on if on else self._icon)
        self.tray.setToolTip(f"{t('app.title')}: {t('tray.state_on' if on else 'tray.state_off')}")

    def toggle_window(self):
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.show_window()

    def show_window(self):
        self.showNormal(); self.raise_(); self.activateWindow()

    def quit_app(self):
        self._quitting = True
        self.close()

    def _autostart_changed(self, on: bool):
        try:
            autostart.set_enabled(on)
        except OSError as e:
            self.autostart_cb.blockSignals(True); self.autostart_cb.setChecked(not on); self.autostart_cb.blockSignals(False)
            self.status.setText(f"{tr('settings.autostart_failed', self.lang)}: {e}")

    @staticmethod
    def _slider(lo, hi, val):
        s = W.QSlider(QtCore.Qt.Horizontal); s.setRange(lo, hi); s.setValue(val); return s

    def retranslate(self):
        t = lambda k: tr(k, self.lang)
        self.setWindowTitle(t("app.title"))
        self.dev_box.setTitle(t("device.title"))
        amp = lambda k: t(k).replace("&", "&&")   # a literal "&", not a keyboard shortcut
        self.gen_box.setTitle(t("settings.general")); self.bg_box.setTitle(amp("settings.background"))
        self.ai_box.setTitle(amp("settings.ai"))
        self.tabs.setTabText(3, t("settings.title"))
        self.tabs.setTabText(0, t("tab.analyzer").replace("&", "&&")); self.tabs.setTabText(1, t("tab.eq"))
        self.tabs.setTabText(2, t("tab.dynamics").replace("&", "&&"))   # "&" is not a shortcut
        self.eq_panel.retranslate(self.lang)
        self.dyn_panel.retranslate(self.lang)
        self.lang_lbl.setText(t("settings.lang"))
        self.tray_cb.setText(t("settings.tray")); self.tray_cb.setToolTip(t("settings.tray_tip"))
        self.autostart_cb.setText(t("settings.autostart"))
        self.autostart_cb.setToolTip(t("settings.autostart_tip") if autostart.supported() else t("settings.autostart_na"))
        self.resume_cb.setText(t("settings.resume")); self.resume_cb.setToolTip(t("settings.resume_tip"))
        for w in self.set_notes:
            self.set_notes[w].setText(w.toolTip())
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
        self.gate_on.setText(t("label.gate"))
        self.learn_btn.setText(t("noise.learn")); self.train_btn.setText(t("model.check"))
        self.contrib_cb.setText(t("contrib.offer")); self.contrib_del.setText(t("contrib.delete"))
        on = contribute.enabled()
        self.contrib_cb.setVisible(on)
        self.contrib_del.setVisible(on and int(contribute.load_state().get("sent", 0)) > 0)
        self.hint.setText(t("hint.virtualmic"))
        if hasattr(self, "tray"):
            self._update_tray()

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
        self.data["exclusive"] = self.excl.isChecked()
        self.data["tab"] = self.tabs.currentIndex()
        self.data["close_to_tray"] = self.tray_cb.isChecked()
        self.data["resume"] = self.resume_cb.isChecked()
        self.data["geometry"] = bytes(self.saveGeometry().toBase64()).decode("ascii")
        try: settings.save(self.data)
        except OSError: pass

    def _eq_presets_changed(self, presets: dict):
        self.data["eq_presets"] = presets
        self._save()

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
                self.engine = None
                self.status.setText(f"{t('engine.error')}: {e}")
                if not self.isVisible() and self.tray.isVisible():   # started hidden at sign-in
                    self.tray.showMessage(t("app.title"), f"{t('engine.error')}: {e}", W.QSystemTrayIcon.Warning)
                on = None   # failed: keep the remembered on/off state (e.g. USB mic not plugged in yet)
        else:
            if self.engine: self.engine.stop(); self.engine = None
        if on is not None:
            self.data["running"] = on
        on = bool(on)
        for w in (self.in_cb, self.out_cb, self.refresh_btn, self.excl): w.setEnabled(not on)
        self.start_btn.setText(t("engine.stop") if on else t("engine.start"))
        self._update_tray()
        self._save()

    def learn_noise(self):
        sp = self.pipe.spectral
        sp.start_learning()
        self._capturing = bool(contribute.enabled() and self.contrib_cb.isChecked() and self.engine
                               and hasattr(self.pipe, "capture_start"))
        if self._capturing:
            self.pipe.capture_start(LEARN_SECONDS * SAMPLE_RATE)
        self.learn_btn.setEnabled(False)
        self.learn_btn.setText(tr("noise.learning", self.lang).format(s=LEARN_SECONDS))
        QtCore.QTimer.singleShot(LEARN_SECONDS * 1000, self._finish_learn)

    def _finish_learn(self):
        self.pipe.spectral.finish_learning()
        self.learn_btn.setEnabled(True); self.retranslate()
        self.status.setText(tr("noise.learned", self.lang))
        if self._capturing:
            self._capturing = False
            raw, dropped = self.pipe.capture_stop()
            import threading   # screening runs the AI model once: keep it off the UI thread
            threading.Thread(target=lambda: self._sample_signal.ready.emit(contribute.prepare(raw, dropped)),
                             daemon=True, name="screen-sample").start()

    def _offer_sample(self, sample):
        if sample is None:
            return                       # voice detected, too quiet, gaps...: never offered
        dlg = ContributeDialog(sample, self.lang, self)
        if dlg.exec() == W.QDialog.Accepted and dlg.category:
            self.status.setText(tr("contrib.sending", self.lang))
            self._uploader.run(contribute.upload, sample, dlg.category)
        elif dlg.never:
            self.contrib_cb.setChecked(False)

    def _delete_samples(self):
        if W.QMessageBox.question(self, tr("contrib.title", self.lang),
                                  tr("contrib.delete_confirm", self.lang)) == W.QMessageBox.Yes:
            self._uploader.run(contribute.delete_my_samples)

    def _upload_done(self, ok, msg):
        self.retranslate()
        self.status.setText(tr("contrib.thanks" if ok else "contrib.failed", self.lang)
                            + ("" if ok else f": {msg}"))

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
        if self.tabs.currentIndex() == 1:
            self.eq_panel.set_spectrum(o_db)
        elif self.tabs.currentIndex() == 2 and hasattr(p, "dynamics_gr_db"):
            self.dyn_panel.set_meters(p.in_analyzer.level_db(), *p.dynamics_gr_db())
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
        if not self._quitting and self.tray_cb.isChecked() and self.tray.isVisible():
            e.ignore()                      # keep filtering in the background
            self.hide()
            self._save()
            if not self.data.get("tray_hint_shown"):
                self.tray.showMessage(tr("app.title", self.lang), tr("tray.hidden", self.lang), self._icon, 6000)
                self.data["tray_hint_shown"] = True
                self._save()
            return
        self._shutdown()
        super().closeEvent(e)
        W.QApplication.instance().quit()

    def _shutdown(self):
        """Stop audio and save once; the remembered on/off state stays as it was."""
        if self._shut_down:
            return
        self._shut_down = True
        self._save()
        if self.engine: self.engine.stop(); self.engine = None
        self.tray.hide()
