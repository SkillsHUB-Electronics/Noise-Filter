"""Dynamics tab: compressor (with its transfer curve) and limiter, plus gain-reduction meters."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets as W

from ..core.dynamics import static_curve_db
from ..i18n import tr

# (config key, slider min, max, scale, format) - slider value = setting * scale
COMP_PARAMS = [
    ("comp_threshold_db", -60, 0, 1, "{:.0f} dB"),
    ("comp_ratio", 10, 200, 10, "{:.1f} : 1"),
    ("comp_attack_ms", 1, 100, 1, "{:.0f} ms"),
    ("comp_release_ms", 20, 1000, 1, "{:.0f} ms"),
    ("comp_makeup_db", 0, 24, 1, "+{:.0f} dB"),
]
LIM_PARAMS = [("limiter_ceiling_db", -24, 0, 2, "{:.1f} dBFS")]
X_DB = np.linspace(-60, 0, 241)


def gr_bar():
    b = W.QProgressBar()
    b.setRange(0, 240)                  # tenths of a dB, 0..24 dB
    b.setTextVisible(True)
    b.setFormat("0.0 dB")
    b.setStyleSheet("QProgressBar::chunk { background: #e0a030; }")
    return b


class DynamicsPanel(W.QWidget):
    changed = QtCore.Signal(dict)       # PipelineConfig fields to update

    def __init__(self, cfg, lang: str, parent=None):
        super().__init__(parent)
        self.lang = lang
        self.cfg = cfg
        self.sliders, self.vals, self.lbls = {}, {}, {}
        lay = W.QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)

        left = W.QVBoxLayout()
        self.comp_box = W.QGroupBox()
        g = W.QGridLayout(self.comp_box)
        self.comp_on = W.QCheckBox(); self.comp_on.setChecked(cfg.comp_enabled)
        g.addWidget(self.comp_on, 0, 0, 1, 3)
        self._rows(g, COMP_PARAMS, start=1)
        g.setColumnStretch(1, 1)
        left.addWidget(self.comp_box)

        self.lim_box = W.QGroupBox()
        lg = W.QGridLayout(self.lim_box)
        self.lim_on = W.QCheckBox(); self.lim_on.setChecked(cfg.limiter_enabled)
        lg.addWidget(self.lim_on, 0, 0, 1, 3)
        self._rows(lg, LIM_PARAMS, start=1)
        lg.setColumnStretch(1, 1)
        left.addWidget(self.lim_box)
        left.addStretch(1)
        lay.addLayout(left, 3)

        right = W.QVBoxLayout()
        self.plot = pg.PlotWidget()
        self.plot.setBackground(None)
        self.plot.setXRange(-60, 0, padding=0); self.plot.setYRange(-60, 0, padding=0)
        self.plot.setMouseEnabled(False, False); self.plot.hideButtons(); self.plot.setMenuEnabled(False)
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setLabel("bottom", "in dBFS"); self.plot.setLabel("left", "out dBFS")
        self.plot.plot(X_DB, X_DB, pen=pg.mkPen("#88888880", width=1, style=QtCore.Qt.DashLine))
        self.curve = self.plot.plot(X_DB, X_DB, pen=pg.mkPen("#f0b030", width=3))
        self.ceiling_line = pg.InfiniteLine(angle=0, pen=pg.mkPen("#e6194b", width=1.5, style=QtCore.Qt.DashLine))
        self.plot.addItem(self.ceiling_line)
        self.dot = pg.ScatterPlotItem(size=11, brush=pg.mkBrush("#30b070"), pen=pg.mkPen("white", width=1.5))
        self.plot.addItem(self.dot)
        self.plot.setMinimumSize(200, 160)
        right.addWidget(self.plot, 1)
        meters = W.QGridLayout()
        self.comp_gr_lbl, self.lim_gr_lbl = W.QLabel(), W.QLabel()
        self.comp_gr, self.lim_gr = gr_bar(), gr_bar()
        meters.addWidget(self.comp_gr_lbl, 0, 0); meters.addWidget(self.comp_gr, 0, 1)
        meters.addWidget(self.lim_gr_lbl, 1, 0); meters.addWidget(self.lim_gr, 1, 1)
        meters.setColumnStretch(1, 1)
        right.addLayout(meters)
        lay.addLayout(right, 2)

        self.comp_on.toggled.connect(lambda v: self._changed(comp_enabled=v))
        self.lim_on.toggled.connect(lambda v: self._changed(limiter_enabled=v))
        self.retranslate(lang)
        self._redraw()

    def _rows(self, g, params, start):
        for r, (key, lo, hi, scale, fmt) in enumerate(params, start=start):
            s = W.QSlider(QtCore.Qt.Horizontal); s.setRange(lo, hi)
            s.setValue(int(round(getattr(self.cfg, key) * scale)))
            lbl, val = W.QLabel(), W.QLabel()
            val.setMinimumWidth(self.fontMetrics().horizontalAdvance("-24.0 dBFS") + 8)
            val.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            s.valueChanged.connect(lambda v, key=key, scale=scale: self._changed(**{key: v / scale}))
            g.addWidget(lbl, r, 0); g.addWidget(s, r, 1); g.addWidget(val, r, 2)
            self.sliders[key], self.vals[key], self.lbls[key] = s, val, lbl
        self._update_vals()

    def retranslate(self, lang: str):
        self.lang = lang
        t = lambda k: tr(k, lang)
        self.comp_box.setTitle(t("dyn.comp")); self.lim_box.setTitle(t("dyn.limiter"))
        self.comp_on.setText(t("dyn.comp_on")); self.lim_on.setText(t("dyn.limiter_on"))
        self.comp_on.setToolTip(t("dyn.comp_tip")); self.lim_on.setToolTip(t("dyn.limiter_tip"))
        for key in self.lbls:
            self.lbls[key].setText(t(f"dyn.{key}"))
        self.comp_gr_lbl.setText(t("dyn.comp_gr")); self.lim_gr_lbl.setText(t("dyn.limiter_gr"))

    def _update_vals(self):
        for key, lo, hi, scale, fmt in COMP_PARAMS + LIM_PARAMS:
            if key in self.vals:
                self.vals[key].setText(fmt.format(self.sliders[key].value() / scale))

    def _changed(self, **kw):
        self._update_vals()
        self.changed.emit(kw)
        self._redraw()

    def _redraw(self):
        c = self.cfg            # the pipeline's live config (already updated by the receiver)
        y = static_curve_db(X_DB, c.comp_threshold_db, c.comp_ratio) + c.comp_makeup_db if c.comp_enabled else X_DB.copy()
        if c.limiter_enabled:
            y = np.minimum(y, c.limiter_ceiling_db)
        self.curve.setData(X_DB, y)
        self.ceiling_line.setValue(c.limiter_ceiling_db)
        self.ceiling_line.setVisible(c.limiter_enabled)
        for key, *_ in COMP_PARAMS:
            self.sliders[key].setEnabled(c.comp_enabled)
        self.sliders["limiter_ceiling_db"].setEnabled(c.limiter_enabled)

    def set_meters(self, in_level_db: float, comp_gr: float, lim_gr: float):
        for bar, v in ((self.comp_gr, comp_gr), (self.lim_gr, lim_gr)):
            v = max(0.0, float(v))
            bar.setValue(int(min(240, v * 10)))
            bar.setFormat(f"{v:.1f} dB")
        x = max(-60.0, min(0.0, in_level_db))
        c = self.cfg
        y = float(static_curve_db(x, c.comp_threshold_db, c.comp_ratio)) + c.comp_makeup_db if c.comp_enabled else x
        if c.limiter_enabled:
            y = min(y, c.limiter_ceiling_db)
        self.dot.setData([x], [y])
