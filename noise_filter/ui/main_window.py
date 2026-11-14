import os
import time
import numpy as np
from PySide6 import QtCore, QtWidgets as W
from ..core import FRAME_SIZE, FRAME_MS, SAMPLE_RATE
from ..core import native
from .. import contribute, model_update
from ..i18n import tr
from . import autostart, icons, settings, theme
from .spectrum_plot import SpectrumPlot
from .widgets import Card, ColorDot, IconButton, LevelMeter, StatusDot, scroll_page, vline
from .eq_panel import EqPanel
from .dynamics_panel import DynamicsPanel
from .contribute_dialog import ContributeDialog, UploadWorker
from .about import AboutCard

LANGS = [("en", "English"), ("id", "Bahasa Indonesia")]
LEARN_SECONDS = 3


class _StatusLabel(W.QLabel):
    """Status-bar message: shown in full as a tooltip, elided in the bar, cleared after a while."""

    def __init__(self):
        super().__init__()
        self._full = ""
        self._clear = QtCore.QTimer(self, singleShot=True, interval=12000, timeout=lambda: self.setText(""))

    def setText(self, text):
        self._full = text or ""
        self.setToolTip(self._full if len(self._full) > 60 else "")
        self._elide()
        if self._full:
            self._clear.start()

    def text(self):
        return self._full

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def _elide(self):
        super().setText(self.fontMetrics().elidedText(self._full, QtCore.Qt.ElideRight, max(20, self.width())))


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
        theme.apply(self.data.get("theme", "light"))
        self._build()
        self._build_tray()
        self.retranslate()
        self.refresh_devices()
        geo = self.data.get("geometry")
        if not (geo and self.restoreGeometry(QtCore.QByteArray.fromBase64(geo.encode("ascii")))):
            self.resize(1180, 800)
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
        c.setObjectName("page")
        root = W.QVBoxLayout(c)
        root.setContentsMargins(16, 10, 16, 10)
        root.setSpacing(10)

        # app header inside the window (the native Windows title bar stays above it)
        head = W.QHBoxLayout(); head.setSpacing(10)
        self.logo = W.QLabel()
        from .app import app_icon
        from PySide6 import QtGui
        self.logo.setPixmap(app_icon(QtGui).pixmap(40, 40))
        titles = W.QVBoxLayout(); titles.setSpacing(0)
        self.app_title = W.QLabel(); self.app_title.setObjectName("appTitle")
        self.app_sub = W.QLabel(); self.app_sub.setObjectName("appSubtitle")
        titles.addWidget(self.app_title); titles.addWidget(self.app_sub)
        head.addWidget(self.logo); head.addLayout(titles); head.addStretch(1)
        root.addLayout(head)

        # devices card: icon + label | combo | extra, two rows; the big Start button on the right
        self.dev_box = Card()
        self.dev_box.header.hide()
        d = self.dev_box.setBodyLayout(W.QGridLayout(), margins=(14, 8, 14, 10))
        d.setHorizontalSpacing(10); d.setVerticalSpacing(6)
        self.dev_title = W.QLabel(); self.dev_title.setObjectName("sectionLabel")
        self.in_lbl, self.out_lbl = W.QLabel(), W.QLabel()
        self.in_lbl.setObjectName("strong"); self.out_lbl.setObjectName("strong")
        self.in_ico, self.out_ico = W.QLabel(), W.QLabel()
        self.in_cb, self.out_cb = W.QComboBox(), W.QComboBox()
        for cb in (self.in_cb, self.out_cb):     # long device names must not widen the window
            cb.setSizeAdjustPolicy(W.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            cb.setMinimumContentsLength(18)
            cb.setSizePolicy(W.QSizePolicy.Expanding, W.QSizePolicy.Fixed)
        self.refresh_btn = W.QPushButton()
        IconButton.set(self.refresh_btn, "refresh")
        self.excl = W.QCheckBox(); self.excl.setChecked(bool(self.data.get("exclusive", False)))
        self.excl.toggled.connect(lambda _: self._save())
        self.start_btn = W.QPushButton(); self.start_btn.setCheckable(True)
        self.start_btn.setObjectName("primary")
        self.start_btn.setMinimumWidth(130)
        self.start_btn.setSizePolicy(W.QSizePolicy.Preferred, W.QSizePolicy.Expanding)
        IconButton.set(self.start_btn, "play", "#ffffff", size=18)
        d.addWidget(self.dev_title, 0, 0, 1, 3)
        for r, (ico, lbl, cb, extra) in enumerate(((self.in_ico, self.in_lbl, self.in_cb, self.refresh_btn),
                                                   (self.out_ico, self.out_lbl, self.out_cb, self.excl)), start=1):
            row = W.QHBoxLayout(); row.setSpacing(8); row.addWidget(ico); row.addWidget(lbl)
            d.addLayout(row, r, 0); d.addWidget(cb, r, 1); d.addWidget(extra, r, 2)
        d.addWidget(self.start_btn, 0, 3, 3, 1)
        d.setColumnStretch(1, 1)
        root.addWidget(self.dev_box)
        self.refresh_btn.clicked.connect(self.refresh_devices)
        self.start_btn.toggled.connect(self.toggle_engine)

        # every tab owns its controls: spectra + filter, EQ, dynamics, settings
        self.tabs = W.QTabWidget()
        self.tabs.setIconSize(QtCore.QSize(18, 18))
        self.tabs.setDocumentMode(True)
        spec_tab = W.QWidget(); spec_tab.setObjectName("page")
        self._spec_lay = W.QVBoxLayout(spec_tab)
        self._spec_lay.setContentsMargins(0, 10, 0, 4)
        self._spec_lay.setSpacing(12)
        plots = W.QHBoxLayout(); plots.setSpacing(12)
        self._spec_lay.addLayout(plots, 1)
        freqs = self.pipe.in_analyzer.freqs
        self.in_plot = SpectrumPlot("", "spec_in", freqs)
        self.out_plot = SpectrumPlot("", "spec_out", freqs)
        self.spec_cards = []
        for p, key in ((self.in_plot, "spec_in"), (self.out_plot, "spec_out")):
            p.setMinimumHeight(120)
            card = Card()
            card.header.setObjectName("plainHeader")
            dot = ColorDot(theme.tok(key)); card.header_lay.insertWidget(0, dot)
            card._dot, card._key = dot, key
            card.setBodyLayout(W.QVBoxLayout(), margins=(6, 0, 10, 6)).addWidget(p)
            plots.addWidget(card)
            self.spec_cards.append(card)
        self.tabs.addTab(spec_tab, "")
        cfg0 = self.pipe.cfg
        self.eq_panel = EqPanel(freqs, cfg0.eq_enabled, cfg0.eq_bands, self.data.get("eq_presets", {}), self.lang,
                                selection=self.data.get("eq_preset_sel", []), locked=self.data.get("eq_locked", False))
        self.eq_panel.setObjectName("page")
        self.eq_panel.layout().setContentsMargins(0, 0, 0, 4)
        self.eq_panel.changed.connect(lambda on, bands: self._set(eq_enabled=on, eq_bands=bands))
        self.eq_panel.presets_changed.connect(self._eq_presets_changed)
        self.eq_panel.selection_changed.connect(self._eq_selection_changed)
        self.eq_panel.lock_changed.connect(self._eq_lock_changed)
        self.tabs.addTab(self.eq_panel, "")
        self.dyn_panel = DynamicsPanel(self.pipe.cfg, self.lang)
        self.dyn_panel.changed.connect(lambda kw: self._set(**kw))
        self.tabs.addTab(scroll_page(self.dyn_panel), "")
        root.addWidget(self.tabs, 1)

        # filter card: label | slider | value, one row each
        box = Card("funnel"); self.ctrl_box = box
        g = box.setBodyLayout(W.QGridLayout(), margins=(16, 10, 16, 12))
        g.setHorizontalSpacing(16)
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
        val_w = self.fontMetrics().horizontalAdvance("-100 dB") + 12
        for v in self.vals.values():
            v.setObjectName("value")
            v.setMinimumWidth(val_w); v.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.learn_btn, self.train_btn = W.QPushButton(), W.QPushButton()
        self.contrib_rec = W.QPushButton()      # F3 "Record noise": next to Learn noise, spectrum stays visible
        IconButton.set(self.learn_btn, "book"); IconButton.set(self.train_btn, "download")
        IconButton.set(self.contrib_rec, "record", "red")
        self.train_btn.clicked.connect(lambda: self._check_model_update(manual=True))
        # one column: label | control | value, every slider the same width, in signal-chain order
        top = W.QHBoxLayout(); top.addWidget(self.bypass); top.addStretch(1)
        top.addWidget(self.contrib_rec); top.addWidget(self.learn_btn)
        g.addLayout(top, 0, 0, 1, 3)
        g.addWidget(self.lbls["mode"], 1, 0); g.addWidget(self.mode_cb, 1, 1, 1, 2)
        for r, (lbl, sl_, k) in enumerate(((self.lbls["strength"], self.strength, "strength"),
                                           (self.lbls["hp"], self.hp, "hp"),
                                           (self.gate_on, self.gate_th, "gate"),
                                           (self.lbls["gain"], self.gain, "gain")), start=2):
            g.addWidget(lbl, r, 0); g.addWidget(sl_, r, 1); g.addWidget(self.vals[k], r, 2)
        g.setColumnStretch(1, 1)
        g.setVerticalSpacing(6)
        self._spec_lay.addWidget(box)

        # F3: offer to send the 'Learn noise' recording (only when the intake service is configured)
        self.contrib_cb, self.contrib_del, self.contrib_file = W.QCheckBox(), W.QPushButton(), W.QPushButton()
        IconButton.set(self.contrib_file, "upload"); IconButton.set(self.contrib_del, "trash")
        self.contrib_file.clicked.connect(self._contribute_file)
        self.contrib_rec.clicked.connect(self._record_noise)
        self.contrib_cb.setChecked(contribute.load_state().get("ask", True))
        self.contrib_cb.toggled.connect(lambda v: contribute.save_state(ask=v))
        self.contrib_del.clicked.connect(self._delete_samples)
        self._sample_signal = _SampleSignal()
        self._sample_signal.ready.connect(self._offer_sample)
        self._file_signal = _SampleSignal()
        self._file_signal.ready.connect(self._offer_file)
        self._rec_signal = _SampleSignal()
        self._rec_signal.ready.connect(self._offer_recording)
        self._rec = None                         # running "Record noise": {t0, total, temp engine}
        self._rec_timer = QtCore.QTimer(self, interval=100, timeout=self._rec_tick)
        self._uploader = UploadWorker()
        self._uploader.done.connect(self._upload_done)
        self._capturing = False

        # Settings tab: general (language, theme); background & startup; AI model; command line
        self.lang_lbl = W.QLabel()
        self.lang_cb = W.QComboBox()
        for code, name in LANGS: self.lang_cb.addItem(name, code)
        self.lang_cb.setCurrentIndex([c_ for c_, _ in LANGS].index(self.lang))
        self.lang_cb.currentIndexChanged.connect(self._lang_changed)
        self.theme_lbl = W.QLabel()
        self.theme_btns = {}
        theme_row = W.QHBoxLayout(); theme_row.setSpacing(0)
        group = W.QButtonGroup(self); group.setExclusive(True)
        for n, (key, ico) in enumerate((("light", "sun"), ("dark", "moon"), ("system", "monitor"))):
            b = W.QPushButton(); b.setCheckable(True)
            b.setProperty("seg", True); b.setProperty("pos", "first" if n == 0 else "last" if n == 2 else "mid")
            IconButton.set(b, ico, "text", "#ffffff")
            b.clicked.connect(lambda _=False, key=key: self._theme_changed(key))
            group.addButton(b); theme_row.addWidget(b)
            self.theme_btns[key] = b
        self.theme_btns[theme.mode()].setChecked(True)
        self.tray_cb = W.QCheckBox(); self.tray_cb.setChecked(bool(self.data.get("close_to_tray", True)))
        self.tray_cb.setEnabled(W.QSystemTrayIcon.isSystemTrayAvailable())
        self.autostart_cb = W.QCheckBox(); self.autostart_cb.setChecked(autostart.is_enabled())
        self.autostart_cb.setEnabled(autostart.supported())
        self.resume_cb = W.QCheckBox(); self.resume_cb.setChecked(bool(self.data.get("resume", True)))
        page = W.QWidget()
        pl = W.QVBoxLayout(page)
        pl.setContentsMargins(0, 10, 0, 4); pl.setSpacing(12)
        self.gen_box, self.bg_box = Card("gear"), Card("power")
        self.ai_box, self.ctl_box = Card("layers"), Card("terminal")   # ctl: command line / MCP control
        cl = self.ctl_box.setBodyLayout(W.QVBoxLayout())
        self.ctl_note = W.QLabel(); self.ctl_note.setWordWrap(True)
        self.ctl_copy = W.QPushButton()
        IconButton.set(self.ctl_copy, "copy")
        self.ctl_copy.clicked.connect(self._copy_mcp_config)
        cl.addWidget(self.ctl_note)
        row = W.QHBoxLayout(); row.addWidget(self.ctl_copy); row.addStretch(1)
        cl.addLayout(row); cl.addStretch(1)
        gl = self.gen_box.setBodyLayout(W.QHBoxLayout())
        gl.setSpacing(14)
        self.lang_cb.setMinimumWidth(200)
        gl.addWidget(self.lang_lbl); gl.addWidget(self.lang_cb, 1); gl.addSpacing(10); gl.addWidget(vline())
        gl.addSpacing(10); gl.addWidget(self.theme_lbl); gl.addLayout(theme_row); gl.addStretch(1)
        bl = self.bg_box.setBodyLayout(W.QGridLayout())
        bl.setHorizontalSpacing(10); bl.setVerticalSpacing(0)
        self.set_notes = {}
        for r, w in enumerate((self.tray_cb, self.autostart_cb, self.resume_cb)):
            w.setObjectName("strong")
            note = W.QLabel(); note.setWordWrap(True); note.setObjectName("note")
            note.setContentsMargins(26, 0, 0, 8)
            bl.addWidget(w, 2 * r, 0); bl.addWidget(note, 2 * r + 1, 0)
            self.set_notes[w] = note
        al = self.ai_box.setBodyLayout(W.QVBoxLayout())
        al.setSpacing(8)
        row = W.QHBoxLayout(); row.addWidget(self.train_btn); row.addStretch(1)
        al.addLayout(row)
        al.addWidget(self.contrib_cb)
        row = W.QHBoxLayout(); row.addWidget(self.contrib_file); row.addWidget(self.contrib_del); row.addStretch(1)
        al.addLayout(row); al.addStretch(1)
        pl.addWidget(self.gen_box)
        pl.addWidget(self.bg_box)
        pair = W.QHBoxLayout(); pair.setSpacing(12)
        pair.addWidget(self.ai_box, 1); pair.addWidget(self.ctl_box, 1)
        pl.addLayout(pair)
        self.about_box = AboutCard()     # version, copyright, privacy policy, license
        pl.addWidget(self.about_box)
        pl.addStretch(1)
        self.set_box = scroll_page(page)
        self.tabs.addTab(self.set_box, "")
        self._tab_icons = ("wave", "sliders", "gauge", "gear")
        self._style_tabs()
        theme.notifier.changed.connect(self._restyle)
        self.tabs.setCurrentIndex(int(self.data.get("tab", 0)) % self.tabs.count())
        self.tabs.currentChanged.connect(lambda _: self._save())
        self.tray_cb.toggled.connect(lambda _: self._save())
        self.resume_cb.toggled.connect(lambda _: self._save())
        self.autostart_cb.toggled.connect(self._autostart_changed)

        # bottom status bar: state | engine | xruns | DSP | latency | message ......... level meter
        bar = W.QFrame(); bar.setObjectName("statusBar")
        sl = W.QHBoxLayout(bar); sl.setContentsMargins(8, 5, 8, 5); sl.setSpacing(10)
        pill = W.QFrame(); pill.setObjectName("pill")
        pll = W.QHBoxLayout(pill); pll.setContentsMargins(8, 3, 10, 3); pll.setSpacing(6)
        self.state_dot = StatusDot(); self.state_lbl = W.QLabel(); self.state_lbl.setObjectName("strong")
        pll.addWidget(self.state_dot); pll.addWidget(self.state_lbl)
        sl.addWidget(pill)
        self.stat_lbls = {k: W.QLabel() for k in ("engine", "xruns", "dsp", "latency")}
        self.stat_seps = []
        for k, lbl in self.stat_lbls.items():
            sep = W.QLabel("|"); sep.setObjectName("statusSep")
            self.stat_seps.append(sep)
            sl.addWidget(sep); sl.addWidget(lbl)
        self.status = _StatusLabel()   # messages; long text must never force the window wider
        self.status.setObjectName("muted")
        self.status.setSizePolicy(W.QSizePolicy.Ignored, W.QSizePolicy.Preferred)
        sl.addSpacing(6)
        sl.addWidget(self.status, 1)
        mp = W.QFrame(); mp.setObjectName("pill")
        mpl = W.QHBoxLayout(mp); mpl.setContentsMargins(8, 3, 8, 3); mpl.setSpacing(8)
        self.meter_ico = W.QLabel(); self.meter = LevelMeter()
        mpl.addWidget(self.meter_ico); mpl.addWidget(self.meter)
        sl.addWidget(mp)
        root.addWidget(bar)
        self.statusBar().hide()

        self.bypass.toggled.connect(lambda v: self._set(bypass=v))
        self.mode_cb.currentIndexChanged.connect(lambda _: self._mode_changed(self.mode_cb.currentData()))
        self.strength.valueChanged.connect(lambda v: self._set(strength=v / 100))
        self.hp.valueChanged.connect(lambda v: self._set(highpass_hz=float(v)))
        self.gate_on.toggled.connect(lambda v: self._set(gate_enabled=v))
        self.gate_th.valueChanged.connect(lambda v: self._set(gate_threshold_db=float(v)))
        self.gain.valueChanged.connect(lambda v: self._set(output_gain_db=float(v)))
        self.learn_btn.clicked.connect(self.learn_noise)
        self._update_value_labels()
        self._restyle()

    def _style_tabs(self):
        t = theme.tok()
        for i, name in enumerate(self._tab_icons):
            self.tabs.setTabIcon(i, icons.icon(name, t["text"], "#ffffff", size=18))

    def _restyle(self):
        t = theme.tok()
        self._style_tabs()
        self.in_ico.setPixmap(icons.pixmap("mic", t["muted"], 18))
        self.out_ico.setPixmap(icons.pixmap("speaker", t["muted"], 18))
        self.meter_ico.setPixmap(icons.pixmap("wave", t["muted"], 18))
        for card in self.spec_cards:
            card._dot.setColor(t[card._key])
        self._update_state()

    def _theme_changed(self, mode: str):
        self.data["theme"] = mode
        theme.apply(mode)
        self._save()

    def _update_state(self):
        on = self.engine is not None
        t = theme.tok()
        key = "status.running" if on else "status.demo" if self.demo else "status.stopped"
        self.state_lbl.setText(tr(key, self.lang))
        self.state_dot.setColor(t["green_lit"] if on or self.demo else t["disabled"])

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

    def _copy_mcp_config(self):
        import json
        from ..ctl import mcp_config
        W.QApplication.clipboard().setText(json.dumps(mcp_config(), indent=2))
        self.status.setText(tr("settings.control_copied", self.lang))

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
        self.app_title.setText(t("app.title")); self.app_sub.setText(t("app.subtitle"))
        self.dev_box.setTitle(t("device.title")); self.dev_title.setText(t("device.title"))
        self.theme_lbl.setText(t("settings.theme"))
        for key, b in self.theme_btns.items():
            b.setText(t(f"theme.{key}"))
        amp = lambda k: t(k).replace("&", "&&")   # a literal "&", not a keyboard shortcut
        self.gen_box.setTitle(t("settings.general")); self.bg_box.setTitle(amp("settings.background"))
        self.ai_box.setTitle(amp("settings.ai")); self.ctl_box.setTitle(amp("settings.control"))
        self.ctl_note.setText(t("settings.control_note")); self.ctl_copy.setText(t("settings.control_copy"))
        self.tabs.setTabText(3, t("settings.title"))
        self.tabs.setTabText(0, t("tab.analyzer").replace("&", "&&")); self.tabs.setTabText(1, t("tab.eq"))
        self.tabs.setTabText(2, t("tab.dynamics").replace("&", "&&"))   # "&" is not a shortcut
        self.eq_panel.retranslate(self.lang)
        self.dyn_panel.retranslate(self.lang)
        self.about_box.retranslate(self.lang)
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
        self.spec_cards[0].setTitle(t("analyzer.input")); self.spec_cards[1].setTitle(t("analyzer.output"))
        for p in (self.in_plot, self.out_plot):
            p.set_labels(t("analyzer.axis_level"), t("analyzer.axis_freq"))
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
        self.contrib_file.setText(t("contrib.file"))
        if not self._rec:
            self.contrib_rec.setText(t("contrib.record"))
        on = contribute.enabled()
        self.contrib_cb.setVisible(on)
        self.contrib_file.setVisible(on)
        self.contrib_rec.setVisible(on)
        self.contrib_del.setVisible(on and int(contribute.load_state().get("sent", 0)) > 0)
        for w in (self.out_lbl, self.out_cb):
            w.setToolTip(t("hint.virtualmic"))
        self._update_state()
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
        self.data["theme"] = theme.mode()
        self.data["close_to_tray"] = self.tray_cb.isChecked()
        self.data["resume"] = self.resume_cb.isChecked()
        self.data["geometry"] = bytes(self.saveGeometry().toBase64()).decode("ascii")
        try: settings.save(self.data)
        except OSError: pass

    def _eq_selection_changed(self, sel: list):
        self.data["eq_preset_sel"] = sel
        self._save()

    def _eq_lock_changed(self, locked: bool):
        self.data["eq_locked"] = locked
        self._save()

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

    def _make_engine(self):
        if self.native_engine:
            return native.NativeEngine(self.pipe, self.in_cb.currentData(),
                                       self.out_cb.currentData(), exclusive=self.excl.isChecked())
        from ..audio.engine import Engine
        return Engine(self.pipe, self.in_cb.currentData(), self.out_cb.currentData(),
                      exclusive=self.excl.isChecked())

    def toggle_engine(self, on: bool):
        t = lambda k: tr(k, self.lang)
        if on:
            try:
                self.engine = self._make_engine()
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
        IconButton.set(self.start_btn, "stop" if on else "play", "#ffffff", size=18)
        self._update_state()
        self._update_tray()
        self._save()

    def learn_noise(self):
        if self._rec:
            return
        sp = self.pipe.spectral
        sp.start_learning()
        self._capturing = bool(contribute.enabled() and self.contrib_cb.isChecked() and self.engine
                               and hasattr(self.pipe, "capture_start"))
        if self._capturing:
            self.pipe.capture_start(LEARN_SECONDS * SAMPLE_RATE)
        self.learn_btn.setEnabled(False); self.contrib_rec.setEnabled(False)
        self.learn_btn.setText(tr("noise.learning", self.lang).format(s=LEARN_SECONDS))
        QtCore.QTimer.singleShot(LEARN_SECONDS * 1000, self._finish_learn)

    def _finish_learn(self):
        self.pipe.spectral.finish_learning()
        self.learn_btn.setEnabled(True); self.contrib_rec.setEnabled(True); self.retranslate()
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

    def _record_noise(self):
        """Record a few seconds of room noise from the chosen microphone and offer to send it.
        Runs inline (the button shows the countdown) so the spectrum stays visible. Uses the
        running audio engine, or starts one just for the recording. Clicking again cancels."""
        t = lambda k: tr(k, self.lang)
        if self._rec:
            self._rec_finish(cancel=True)
            return
        temp = None
        if not self.engine:
            if self.in_cb.currentData() is None:
                self._file_failed(t("contrib.record_nomic"))
                return
            try:
                temp = self._make_engine()
                temp.start()
            except Exception as e:
                self._file_failed(f"{t('contrib.record_nomic')} ({e})")
                return
        total = contribute.TRIM_START + contribute.RECORD_SECONDS
        self._rec = {"t0": time.monotonic(), "total": total, "temp": temp}
        self.pipe.capture_start(int(total * SAMPLE_RATE))
        self.learn_btn.setEnabled(False)
        self.status.setText(t("contrib.record_tip"))
        self._rec_timer.start()
        self._rec_tick()

    def _rec_tick(self):
        r = self._rec
        if not r:
            return
        left = r["total"] - (time.monotonic() - r["t0"])
        if left <= 0:
            self._rec_finish()
            return
        self.contrib_rec.setText("■  " + tr("contrib.record_left", self.lang).format(s=int(left + 0.999)))
        self.contrib_rec.setToolTip(tr("contrib.record_tip", self.lang))

    def _rec_finish(self, cancel: bool = False):
        r, self._rec = self._rec, None
        self._rec_timer.stop()
        raw, dropped = self.pipe.capture_stop()
        if r and r["temp"] is not None:
            r["temp"].stop()
        self.learn_btn.setEnabled(True)
        self.retranslate()
        if cancel:
            self.status.setText("")
            return
        self.status.setText(tr("contrib.file_checking", self.lang))
        self.contrib_rec.setEnabled(False)
        import threading    # screening runs the AI model: keep it off the UI thread
        threading.Thread(target=lambda: self._rec_signal.ready.emit(contribute.prepare_with_reason(raw, dropped)),
                         daemon=True, name="screen-recording").start()

    def _offer_recording(self, result):
        sample, reason = result
        self.contrib_rec.setEnabled(True)
        self.status.setText("")
        t = lambda k: tr(k, self.lang)
        if sample is None:
            W.QMessageBox.information(self, t("contrib.title"),
                                      t("contrib.record_none").format(reason=t(f"contrib.reason.{reason}")))
            return
        dlg = ContributeDialog(sample, self.lang, self)
        dlg.never_btn.setVisible(False)      # the user asked for this one: no "don't ask again"
        if dlg.exec() == W.QDialog.Accepted and dlg.category:
            self.status.setText(t("contrib.sending"))
            self._uploader.run(contribute.upload, sample, dlg.category)

    def _contribute_file(self):
        """Let the user send noise from an audio file they recorded themselves."""
        from .audio_file import FILTER, qt_decode
        t = lambda k: tr(k, self.lang)
        path, _ = W.QFileDialog.getOpenFileName(self, t("contrib.file"), "", f"{t('contrib.file_filter')} ({FILTER})")
        if not path:
            return
        self.status.setText(t("contrib.file_checking"))
        self.contrib_file.setEnabled(False)
        W.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            x = contribute.load_audio_file(path, decoder=qt_decode)
        except contribute.AudioFileError as e:
            self._file_failed(t(f"contrib.file_err.{e}"))
            return
        except Exception as e:
            self._file_failed(f"{t('contrib.file_err.unsupported')} ({e})")
            return
        finally:
            W.QApplication.restoreOverrideCursor()
        name = os.path.basename(path)
        import threading    # screening runs the AI model on every clip: keep it off the UI thread
        threading.Thread(target=lambda: self._file_signal.ready.emit((name, *contribute.file_clips(x))),
                         daemon=True, name="screen-file").start()

    def _file_failed(self, text):
        self.contrib_file.setEnabled(True)
        self.status.setText(text)
        W.QMessageBox.information(self, tr("contrib.title", self.lang), text)

    def _offer_file(self, result):
        name, clips, dropped = result
        t = lambda k: tr(k, self.lang)
        if not clips:
            reason = max(dropped, key=dropped.get) if dropped else "silent"
            self._file_failed(t("contrib.file_none").format(reason=t(f"contrib.reason.{reason}")))
            return
        self.contrib_file.setEnabled(True)
        self.status.setText("")
        info = {"name": name, "clips": len(clips), "dropped": sum(dropped.values())}
        dlg = ContributeDialog(np.concatenate(clips), self.lang, self, file=info)
        if dlg.exec() == W.QDialog.Accepted and dlg.category:
            self.status.setText(t("contrib.sending"))
            self._uploader.run(contribute.upload_clips, clips, dlg.category)

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
        self.meter.setLevel(p.out_analyzer.level_db())
        st = self.stat_lbls
        st["engine"].setText(tr("engine.backend", self.lang).format(name="C++" if self.native else "Python"))
        stats = {}
        if self.engine and hasattr(self.engine, "stats"):
            s = self.engine.stats()
            stats = {"xruns": f"xruns: {s['xruns']}",
                     "dsp": f"DSP: {s['dsp_avg_us'] / 1000:.2f} ms (max {s['dsp_max_us'] / 1000:.2f}) / {FRAME_MS:.0f} ms",
                     "latency": f"{tr('engine.latency', self.lang)}: ~{s['latency_ms']:.0f} ms"}
        elif self.engine:
            stats = {"xruns": f"xruns: {self.engine.xruns}",
                     "dsp": f"DSP: {FRAME_MS:.0f} ms frames @ {SAMPLE_RATE // 1000} kHz"}
        elif self.demo:
            stats = {"dsp": f"DSP: {getattr(self, '_cost', 0):.2f} ms / {FRAME_MS:.0f} ms"}
        for (k, lbl), sep in zip(list(st.items())[1:], self.stat_seps[1:]):
            lbl.setText(stats.get(k, "")); lbl.setVisible(k in stats); sep.setVisible(k in stats)

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
