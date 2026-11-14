"""Dynamics tab: compressor and limiter cards (slider + number box per setting), the compressor's
transfer curve and the gain-reduction meters."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets as W

from ..core.dynamics import static_curve_db
from ..i18n import tr
from . import theme
from .widgets import Card, ToggleSwitch

# (config key, slider min, max, scale, format) - slider value = setting * scale
COMP_PARAMS = [
    ("comp_threshold_db", -60, 0, 1, "{:.0f} dB"),
    ("comp_ratio", 10, 200, 10, "{:.1f} : 1"),
    ("comp_attack_ms", 1, 100, 1, "{:.0f} ms"),
    ("comp_release_ms", 20, 1000, 1, "{:.0f} ms"),
    ("comp_makeup_db", 0, 24, 1, "+{:.0f} dB"),
]
LIM_PARAMS = [("limiter_ceiling_db", -24, 0, 2, "{:.1f} dBFS")]
# number box next to each slider: decimals, suffix
SPIN = {"comp_threshold_db": (0, " dB"), "comp_ratio": (1, " : 1"), "comp_attack_ms": (0, " ms"),
        "comp_release_ms": (0, " ms"), "comp_makeup_db": (0, " dB"), "limiter_ceiling_db": (1, " dBFS")}
X_DB = np.linspace(-60, 0, 241)


def gr_bar():
    b = W.QProgressBar()
    b.setObjectName("thinBar")
    b.setRange(0, 240)                  # tenths of a dB, 0..24 dB
    b.setTextVisible(False)
    return b


class DynamicsPanel(W.QWidget):
    changed = QtCore.Signal(dict)       # PipelineConfig fields to update

    def __init__(self, cfg, lang: str, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.lang = lang
        self.cfg = cfg
        self.sliders, self.vals, self.lbls = {}, {}, {}
        lay = W.QHBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 4)
        lay.setSpacing(12)

        left = W.QVBoxLayout(); left.setSpacing(12)
        self.comp_box = Card("compressor")
        self.comp_on = ToggleSwitch(); self.comp_on.setChecked(cfg.comp_enabled)
        self.comp_box.addHeaderWidget(self.comp_on)
        g = self.comp_box.setBodyLayout(W.QGridLayout())
        self._rows(g, COMP_PARAMS, start=0)
        self._grids = [g]
        left.addWidget(self.comp_box)

        self.lim_box = Card("shield")
        self.lim_on = ToggleSwitch(); self.lim_on.setChecked(cfg.limiter_enabled)
        self.lim_box.addHeaderWidget(self.lim_on)
        lg = self.lim_box.setBodyLayout(W.QGridLayout())
        self._rows(lg, LIM_PARAMS, start=0)
        self._grids.append(lg)
        left.addWidget(self.lim_box)
        left.addStretch(1)
        lay.addLayout(left, 3)

        self.curve_box = Card("curve")
        right = self.curve_box.setBodyLayout(W.QVBoxLayout(), margins=(10, 8, 14, 12))
        self.plot = pg.PlotWidget()
        self.plot.setXRange(-61.5, 1.5, padding=0); self.plot.setYRange(-61.5, 1.5, padding=0)   # edge labels stay visible
        self.plot.setMouseEnabled(False, False); self.plot.hideButtons(); self.plot.setMenuEnabled(False)
        ticks = [[(v, str(v)) for v in range(-60, 1, 10)], [(v, "") for v in range(-55, 0, 10)]]
        for side in ("left", "bottom"):        # one label every 10 dB, grid every 5 dB: no repeated labels
            self.plot.getAxis(side).setTicks(ticks)
        self.unity = self.plot.plot(X_DB, X_DB)
        self.curve = self.plot.plot(X_DB, X_DB, fillLevel=-60)
        self.ceiling_line = pg.InfiniteLine(angle=0)
        self.plot.addItem(self.ceiling_line)
        self.knee = pg.ScatterPlotItem(size=9)
        self.plot.addItem(self.knee)
        self.dot = pg.ScatterPlotItem(size=11)
        self.plot.addItem(self.dot)
        self.plot.setMinimumSize(220, 180)
        right.addWidget(self.plot, 1)
        meters = W.QGridLayout()
        meters.setHorizontalSpacing(12)
        self.comp_gr_lbl, self.lim_gr_lbl = W.QLabel(), W.QLabel()
        self.comp_gr, self.lim_gr = gr_bar(), gr_bar()
        self.comp_gr_val, self.lim_gr_val = W.QLabel("0.0 dB"), W.QLabel("0.0 dB")
        vw = self.fontMetrics().horizontalAdvance("24.0 dB") + 6
        for r, (lbl, bar, val) in enumerate(((self.comp_gr_lbl, self.comp_gr, self.comp_gr_val),
                                             (self.lim_gr_lbl, self.lim_gr, self.lim_gr_val))):
            val.setMinimumWidth(vw); val.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            meters.addWidget(lbl, r, 0); meters.addWidget(bar, r, 1); meters.addWidget(val, r, 2)
        meters.setColumnStretch(1, 1)
        right.addSpacing(6)
        right.addLayout(meters)
        lay.addWidget(self.curve_box, 2)

        self.comp_on.toggled.connect(lambda v: self._changed(comp_enabled=v))
        self.lim_on.toggled.connect(lambda v: self._changed(limiter_enabled=v))
        theme.notifier.changed.connect(self._apply_theme)
        self._labels = ("", "")
        self.retranslate(lang)
        self._apply_theme()
        self._redraw()

    def _rows(self, g, params, start):
        g.setHorizontalSpacing(14); g.setVerticalSpacing(8)
        for r, (key, lo, hi, scale, fmt) in enumerate(params, start=start):
            s = W.QSlider(QtCore.Qt.Horizontal); s.setRange(lo, hi)
            s.setValue(int(round(getattr(self.cfg, key) * scale)))
            dec, suffix = SPIN[key]
            box = W.QDoubleSpinBox()
            box.setDecimals(dec); box.setSuffix(suffix); box.setKeyboardTracking(False)
            box.setRange(lo / scale, hi / scale); box.setSingleStep(1 / scale)
            box.setValue(s.value() / scale)
            box.setMinimumWidth(box.fontMetrics().horizontalAdvance("-24.0 dBFS") + 40)
            box.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
            lbl = W.QLabel()
            s.valueChanged.connect(lambda v, key=key, scale=scale: self._changed(**{key: v / scale}))
            box.valueChanged.connect(lambda v, s=s, scale=scale: s.setValue(int(round(v * scale))))
            g.addWidget(lbl, r, 0); g.addWidget(s, r, 1); g.addWidget(box, r, 2)
            self.sliders[key], self.vals[key], self.lbls[key] = s, box, lbl
        g.setColumnStretch(1, 1)
        self._update_vals()

    def retranslate(self, lang: str):
        self.lang = lang
        t = lambda k: tr(k, lang)
        self.comp_box.setTitle(t("dyn.comp")); self.lim_box.setTitle(t("dyn.limiter"))
        self.curve_box.setTitle(t("dyn.curve"))
        self.comp_on.setText(t("dyn.comp_on")); self.lim_on.setText(t("dyn.limiter_on"))
        self.comp_on.updateGeometry(); self.lim_on.updateGeometry()
        self.comp_on.setToolTip(t("dyn.comp_tip")); self.lim_on.setToolTip(t("dyn.limiter_tip"))
        for key in self.lbls:
            self.lbls[key].setText(t(f"dyn.{key}"))
        self.comp_gr_lbl.setText(t("dyn.comp_gr")); self.lim_gr_lbl.setText(t("dyn.limiter_gr"))
        w = max(l.sizeHint().width() for l in self.lbls.values()) + 8   # sliders of both boxes line up
        for g in self._grids:
            g.setColumnMinimumWidth(0, w)
        self._labels = (t("dyn.axis_out"), t("dyn.axis_in"))
        theme.style_plot(self.plot, *self._labels)

    def _apply_theme(self):
        t = theme.tok()
        theme.style_plot(self.plot, *self._labels)
        self.unity.setPen(pg.mkPen(t["axis"], width=1, style=QtCore.Qt.DashLine))
        self.curve.setPen(pg.mkPen(t["accent"], width=2.5))
        self.curve.setBrush(pg.mkBrush(t["accent"] + "38"))
        self.ceiling_line.setPen(pg.mkPen(t["red"], width=1.5, style=QtCore.Qt.DashLine))
        self.knee.setBrush(pg.mkBrush(t["plot_bg"])); self.knee.setPen(pg.mkPen(t["accent"], width=2))
        self.dot.setBrush(pg.mkBrush(t["green_lit"])); self.dot.setPen(pg.mkPen(t["plot_bg"], width=1.5))

    def _update_vals(self):
        for key, lo, hi, scale, fmt in COMP_PARAMS + LIM_PARAMS:
            if key in self.vals:
                box = self.vals[key]
                box.blockSignals(True); box.setValue(self.sliders[key].value() / scale); box.blockSignals(False)

    def _changed(self, **kw):
        self._update_vals()
        self.changed.emit(kw)
        self._redraw()

    def _out_db(self, x):
        c = self.cfg
        y = static_curve_db(x, c.comp_threshold_db, c.comp_ratio) + c.comp_makeup_db if c.comp_enabled else x
        if c.limiter_enabled:
            y = np.minimum(y, c.limiter_ceiling_db)
        return y

    def _redraw(self):
        c = self.cfg            # the pipeline's live config (already updated by the receiver)
        self.curve.setData(X_DB, self._out_db(X_DB.copy()))
        self.ceiling_line.setValue(c.limiter_ceiling_db)
        self.ceiling_line.setVisible(c.limiter_enabled)
        if c.comp_enabled:
            th = float(c.comp_threshold_db)
            self.knee.setData([th], [float(self._out_db(np.array([th]))[0])])
        else:
            self.knee.setData([], [])
        for key, *_ in COMP_PARAMS:
            self.sliders[key].setEnabled(c.comp_enabled)
            self.vals[key].setEnabled(c.comp_enabled)
        self.sliders["limiter_ceiling_db"].setEnabled(c.limiter_enabled)
        self.vals["limiter_ceiling_db"].setEnabled(c.limiter_enabled)

    def set_meters(self, in_level_db: float, comp_gr: float, lim_gr: float):
        for bar, val, v in ((self.comp_gr, self.comp_gr_val, comp_gr), (self.lim_gr, self.lim_gr_val, lim_gr)):
            v = max(0.0, float(v))
            bar.setValue(int(min(240, v * 10)))
            val.setText(f"{v:.1f} dB")
        x = max(-60.0, min(0.0, in_level_db))
        self.dot.setData([x], [float(self._out_db(np.array([x]))[0])])
