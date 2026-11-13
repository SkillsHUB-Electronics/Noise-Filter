"""Equalizer tab: EQ curve with draggable band points over the output spectrum,
a band table, and presets (built-in + the user's own)."""
from __future__ import annotations

import copy

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets as W

from ..core import eq
from ..i18n import tr
from .spectrum_plot import FreqAxis

COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4", "#f032e6", "#9a6324"]
Y_MIN, Y_MAX = -24.0, 24.0
CURVE_F = np.logspace(np.log10(20), np.log10(20000), 400)


def _spec_to_eq_y(db: np.ndarray) -> np.ndarray:
    """Draw the output spectrum (-100..0 dBFS) in the EQ's -24..+24 dB space."""
    return (np.clip(db, -100, 0) + 100) * (Y_MAX - Y_MIN) / 100 + Y_MIN


class BandHandle(pg.TargetItem):
    """Draggable point of one band. Scroll changes Q."""
    wheeled = QtCore.Signal(object, int)

    def wheelEvent(self, ev):
        self.wheeled.emit(self, 1 if ev.delta() > 0 else -1)
        ev.accept()


class EqPlot(pg.PlotWidget):
    double_clicked = QtCore.Signal(float, float)   # freq Hz, gain dB

    def __init__(self, freqs: np.ndarray):
        super().__init__(axisItems={"bottom": FreqAxis("bottom")})
        self.setBackground(None)
        self.setXRange(np.log10(20), np.log10(20000), padding=0)
        self.setYRange(Y_MIN, Y_MAX, padding=0)
        self.setMouseEnabled(False, False)
        self.hideButtons()
        self.setMenuEnabled(False)
        self.showGrid(x=True, y=True, alpha=0.25)
        self.setLabel("left", "dB")
        self.setLabel("bottom", "Hz")
        self.sx = np.log10(np.maximum(freqs, 1.0))
        self.spec = self.plot(self.sx, np.full_like(self.sx, Y_MIN), pen=pg.mkPen("#30b07060", width=1),
                              fillLevel=Y_MIN, brush=pg.mkBrush("#30b07025"))
        self.addItem(pg.InfiniteLine(0, angle=0, pen=pg.mkPen("#88888880", width=1)))
        self.band_curves: list[pg.PlotDataItem] = []
        self.curve = self.plot(np.log10(CURVE_F), np.zeros_like(CURVE_F), pen=pg.mkPen("#f0b030", width=3))

    def mouseDoubleClickEvent(self, ev):
        p = self.plotItem.vb.mapSceneToView(self.mapToScene(ev.position().toPoint()))
        self.double_clicked.emit(float(10 ** p.x()), float(p.y()))
        ev.accept()


class EqPanel(W.QWidget):
    changed = QtCore.Signal(bool, list)        # enabled, bands
    presets_changed = QtCore.Signal(dict)      # the user's own presets

    def __init__(self, freqs: np.ndarray, enabled: bool, bands: list[dict], user_presets: dict, lang: str,
                 parent=None):
        super().__init__(parent)
        self.lang = lang
        self.bands = [eq.normalize(b) for b in bands][:eq.MAX_BANDS]
        self.user_presets = {k: [eq.normalize(b) for b in v] for k, v in (user_presets or {}).items()}
        self.handles: list[BandHandle] = []
        self._selected = -1

        lay = W.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        top = W.QHBoxLayout()
        self.enable_cb = W.QCheckBox(); self.enable_cb.setChecked(enabled)
        self.preset_lbl = W.QLabel()
        self.preset_cb = W.QComboBox()
        self.preset_cb.setSizeAdjustPolicy(W.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.preset_cb.setMinimumContentsLength(14)
        self.save_btn, self.del_btn, self.add_btn = W.QPushButton(), W.QPushButton(), W.QPushButton()
        top.addWidget(self.enable_cb); top.addSpacing(12)
        top.addWidget(self.preset_lbl); top.addWidget(self.preset_cb, 1)
        top.addWidget(self.save_btn); top.addWidget(self.del_btn)
        top.addStretch(0); top.addWidget(self.add_btn)
        lay.addLayout(top)

        self.plot = EqPlot(freqs)
        lay.addWidget(self.plot, 3)
        self.plot.setMinimumHeight(120)
        self.hint = W.QLabel(); self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: palette(placeholder-text);")
        lay.addWidget(self.hint)

        self.table = W.QTableWidget(0, 7)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(W.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(W.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(W.QAbstractItemView.NoEditTriggers)
        h = self.table.horizontalHeader()
        # cell widgets do not size their columns: give each a width that fits its widget
        fm = self.fontMetrics()
        widths = {0: fm.horizontalAdvance("Aktif") + 40, 2: fm.horizontalAdvance("20000 Hz") + 44,
                  3: fm.horizontalAdvance("-24.0 dB") + 44, 4: fm.horizontalAdvance("18.00") + 44,
                  5: fm.horizontalAdvance("48 dB/oct") + 40, 6: 34}
        for col in range(7):
            h.setSectionResizeMode(col, W.QHeaderView.Stretch if col == 1 else W.QHeaderView.Fixed)
            if col in widths:
                h.resizeSection(col, widths[col])
        self.table.verticalHeader().setDefaultSectionSize(fm.height() + 14)
        self.table.setMinimumHeight(fm.height() * 2 + 3 * (fm.height() + 14) // 2)
        lay.addWidget(self.table, 2)

        self.enable_cb.toggled.connect(lambda _: self._emit())
        self.add_btn.clicked.connect(lambda: self.add_band())
        self.save_btn.clicked.connect(self._save_preset)
        self.del_btn.clicked.connect(self._delete_preset)
        self.preset_cb.activated.connect(self._preset_chosen)
        self.plot.double_clicked.connect(lambda f, g: self.add_band(eq.band("peak", f, round(g, 1), 1.0)))
        self.table.itemSelectionChanged.connect(self._table_selected)
        self.retranslate(lang)
        self._rebuild()

    # ---------- text ----------
    def retranslate(self, lang: str):
        self.lang = lang
        t = lambda k: tr(k, lang)
        self.enable_cb.setText(t("eq.enable"))
        self.preset_lbl.setText(t("eq.preset"))
        self.save_btn.setText(t("eq.save")); self.del_btn.setText(t("eq.delete_preset"))
        self.add_btn.setText(t("eq.add"))
        self.hint.setText(t("eq.hint"))
        self.table.setHorizontalHeaderLabels([t(f"eq.col.{c}") for c in ("on", "type", "freq", "gain", "q", "slope", "x")])
        self._fill_presets()
        if self.table.rowCount():
            self._rebuild()

    def _fill_presets(self):
        cur = self.preset_cb.currentData()
        self.preset_cb.blockSignals(True)
        self.preset_cb.clear()
        self.preset_cb.addItem(tr("eq.preset_none", self.lang), None)
        for k in eq.PRESETS:
            self.preset_cb.addItem(tr(f"eq.preset.{k}", self.lang), f"builtin:{k}")
        for k in sorted(self.user_presets):
            self.preset_cb.addItem(f"★ {k}", f"user:{k}")
        i = self.preset_cb.findData(cur)
        self.preset_cb.setCurrentIndex(max(0, i))
        self.preset_cb.blockSignals(False)
        self.del_btn.setEnabled(bool(cur and cur.startswith("user:")))

    # ---------- model ----------
    def _emit(self):
        self._redraw()
        self.changed.emit(self.enable_cb.isChecked(), copy.deepcopy(self.bands))

    def set_bands(self, bands: list[dict]):
        self.bands = [eq.normalize(b) for b in bands][:eq.MAX_BANDS]
        self._selected = -1
        self._rebuild()
        self._emit()

    def add_band(self, b: dict | None = None):
        if len(self.bands) >= eq.MAX_BANDS:
            return
        self.bands.append(eq.normalize(b or eq.band("peak", 1000, 0, 1.0)))
        if not self.enable_cb.isChecked():
            self.enable_cb.blockSignals(True); self.enable_cb.setChecked(True); self.enable_cb.blockSignals(False)
        self._rebuild()
        self._select(len(self.bands) - 1)
        self._emit()

    def remove_band(self, i: int):
        if 0 <= i < len(self.bands):
            del self.bands[i]
            self._selected = -1
            self._rebuild()
            self._emit()

    def _edit(self, i: int, **kw):
        if not 0 <= i < len(self.bands):
            return
        b = eq.normalize({**self.bands[i], **kw})
        self.bands[i] = b
        self._sync_row(i)
        self._place_handle(i)
        self._emit()

    # ---------- table ----------
    def _rebuild(self):
        for hdl in self.handles:
            self.plot.removeItem(hdl)
        for c in self.plot.band_curves:
            self.plot.removeItem(c)
        self.handles, self.plot.band_curves = [], []
        self.table.setRowCount(0)          # drops the old cell widgets
        self.table.setRowCount(len(self.bands))
        for i, b in enumerate(self.bands):
            color = COLORS[i % len(COLORS)]
            hdl = BandHandle(pos=(0, 0), size=13, symbol="o", movable=True,
                             pen=pg.mkPen("white", width=1.5), brush=pg.mkBrush(color),
                             hoverBrush=pg.mkBrush(color), label=str(i + 1),
                             labelOpts={"color": color, "offset": (8, -14)})
            hdl.setZValue(10)
            hdl.sigPositionChanged.connect(lambda h, i=i: self._dragged(i, h))
            hdl.sigPositionChangeFinished.connect(lambda h, i=i: self._select(i))
            hdl.wheeled.connect(lambda h, d, i=i: self._edit(i, q=self.bands[i]["q"] * (1.15 if d > 0 else 1 / 1.15)))
            self.plot.addItem(hdl)
            self.handles.append(hdl)
            c = self.plot.plot([], [], pen=pg.mkPen(color + "90", width=1, style=QtCore.Qt.DashLine))
            self.plot.band_curves.append(c)
            self._fill_row(i)
            self._place_handle(i)
        self.add_btn.setEnabled(len(self.bands) < eq.MAX_BANDS)
        self.add_btn.setToolTip("" if len(self.bands) < eq.MAX_BANDS else tr("eq.full", self.lang))
        self._redraw()

    def _fill_row(self, i: int):
        b = self.bands[i]
        t = lambda k: tr(k, self.lang)
        on = W.QCheckBox(); on.setChecked(b["on"])
        on.setStyleSheet(f"QCheckBox {{ color: {COLORS[i % len(COLORS)]}; font-weight: bold; padding-left: 4px; }}")
        on.setText(str(i + 1))
        on.toggled.connect(lambda v, i=i: self._edit(i, on=v))
        typ = W.QComboBox()
        for k in eq.TYPES:
            typ.addItem(t(f"eq.type.{k}"), k)
        typ.setCurrentIndex(eq.TYPES.index(b["type"]))
        typ.currentIndexChanged.connect(lambda _, i=i, w=typ: self._edit(i, type=w.currentData()))
        freq = W.QDoubleSpinBox(); freq.setRange(eq.FREQ_MIN, eq.FREQ_MAX); freq.setDecimals(0)
        freq.setSuffix(" Hz"); freq.setSingleStep(10); freq.setKeyboardTracking(False)
        freq.setStepType(W.QAbstractSpinBox.AdaptiveDecimalStepType)
        freq.valueChanged.connect(lambda v, i=i: self._edit(i, freq=v))
        gain = W.QDoubleSpinBox(); gain.setRange(eq.GAIN_MIN, eq.GAIN_MAX); gain.setDecimals(1)
        gain.setSuffix(" dB"); gain.setSingleStep(0.5); gain.setKeyboardTracking(False)
        gain.valueChanged.connect(lambda v, i=i: self._edit(i, gain=v))
        q = W.QDoubleSpinBox(); q.setRange(eq.Q_MIN, eq.Q_MAX); q.setDecimals(2); q.setSingleStep(0.1)
        q.setKeyboardTracking(False)
        q.valueChanged.connect(lambda v, i=i: self._edit(i, q=v))
        slope = W.QComboBox()
        for s in eq.SLOPES:
            slope.addItem(f"{s} dB/oct", s)
        slope.currentIndexChanged.connect(lambda _, i=i, w=slope: self._edit(i, slope=w.currentData()))
        rm = W.QToolButton(); rm.setText("✕"); rm.setToolTip(t("eq.remove"))
        # deferred: the button is deleted when the table is rebuilt
        rm.clicked.connect(lambda _=False, i=i: QtCore.QTimer.singleShot(0, lambda: self.remove_band(i)))
        for col, w in enumerate((on, typ, freq, gain, q, slope, rm)):
            self.table.setCellWidget(i, col, w)
        self._sync_row(i)

    def _sync_row(self, i: int):
        b = self.bands[i]
        ws = [self.table.cellWidget(i, c) for c in range(7)]
        if any(w is None for w in ws):
            return
        on, typ, freq, gain, q, slope, _ = ws
        for w in ws:
            w.blockSignals(True)
        on.setChecked(b["on"])
        typ.setCurrentIndex(eq.TYPES.index(b["type"]))
        freq.setValue(b["freq"]); gain.setValue(b["gain"]); q.setValue(b["q"])
        slope.setCurrentIndex(eq.SLOPES.index(b["slope"]))
        gain.setEnabled(b["type"] in eq.GAIN_TYPES)
        slope.setEnabled(b["type"] in eq.SLOPE_TYPES)
        q.setEnabled(not (b["type"] in eq.SLOPE_TYPES and b["slope"] > 12))   # steeper = pure Butterworth
        for w in ws:
            w.blockSignals(False)

    # ---------- plot ----------
    def _place_handle(self, i: int):
        b = self.bands[i]
        y = b["gain"] if b["type"] in eq.GAIN_TYPES else 0.0
        hdl = self.handles[i]
        hdl.blockSignals(True)
        hdl.setPos(np.log10(b["freq"]), y)
        hdl.blockSignals(False)
        hdl.setOpacity(1.0 if b["on"] else 0.35)

    def _dragged(self, i: int, hdl):
        p = hdl.pos()
        f = float(10 ** min(np.log10(eq.FREQ_MAX), max(np.log10(eq.FREQ_MIN), p.x())))
        kw = {"freq": round(f, 1 if f < 100 else 0)}
        if self.bands[i]["type"] in eq.GAIN_TYPES:
            kw["gain"] = round(float(min(eq.GAIN_MAX, max(eq.GAIN_MIN, p.y()))), 1)
        self._edit(i, **kw)

    def _redraw(self):
        active = self.enable_cb.isChecked()
        x = np.log10(CURVE_F)
        for b, c in zip(self.bands, self.plot.band_curves):
            c.setData(x, eq.response_db([b], CURVE_F) if b["on"] else np.zeros_like(CURVE_F))
            c.setVisible(active and b["on"])
        total = eq.response_db(self.bands, CURVE_F) if active else np.zeros_like(CURVE_F)
        self.plot.curve.setData(x, np.clip(total, Y_MIN - 30, Y_MAX + 30))
        self.plot.curve.setPen(pg.mkPen("#f0b030" if active else "#888888", width=3))

    def set_spectrum(self, db: np.ndarray):
        self.plot.spec.setData(self.plot.sx, _spec_to_eq_y(db))

    def _select(self, i: int):
        self._selected = i
        self.table.blockSignals(True); self.table.selectRow(i); self.table.blockSignals(False)
        for k, h in enumerate(self.handles):
            h.setZValue(20 if k == i else 10)

    def _table_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self._select(rows[0].row())

    # ---------- presets ----------
    def _preset_chosen(self, idx: int):
        d = self.preset_cb.itemData(idx)
        self.del_btn.setEnabled(bool(d and d.startswith("user:")))
        if not d:
            return
        kind, name = d.split(":", 1)
        bands = eq.PRESETS.get(name, []) if kind == "builtin" else self.user_presets.get(name, [])
        self.enable_cb.blockSignals(True); self.enable_cb.setChecked(bool(bands)); self.enable_cb.blockSignals(False)
        self.set_bands(copy.deepcopy(bands))

    def _save_preset(self):
        name, ok = W.QInputDialog.getText(self, tr("eq.save", self.lang), tr("eq.save_prompt", self.lang))
        name = (name or "").strip()[:40]
        if not ok or not name:
            return
        self.save_preset(name)

    def save_preset(self, name: str):
        self.user_presets[name] = copy.deepcopy(self.bands)
        self._fill_presets()
        self.preset_cb.setCurrentIndex(self.preset_cb.findData(f"user:{name}"))
        self.del_btn.setEnabled(True)
        self.presets_changed.emit(copy.deepcopy(self.user_presets))

    def _delete_preset(self):
        d = self.preset_cb.currentData()
        if d and d.startswith("user:"):
            self.user_presets.pop(d.split(":", 1)[1], None)
            self.preset_cb.setCurrentIndex(0)
            self._fill_presets()
            self.presets_changed.emit(copy.deepcopy(self.user_presets))
