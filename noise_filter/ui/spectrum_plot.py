import numpy as np
import pyqtgraph as pg

from . import theme

TICKS = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]


class FreqAxis(pg.AxisItem):
    """Log-frequency axis: data x is log10(Hz); labels show Hz / kHz."""

    def tickValues(self, minVal, maxVal, size):
        return [(1.0, [np.log10(t) for t in TICKS if minVal - 1e-6 <= np.log10(t) <= maxVal + 1e-6])]

    def tickStrings(self, values, scale, spacing):
        out = []
        for v in values:
            hz = 10 ** v
            out.append(f"{round(hz / 1000):g}k" if hz >= 999 else f"{round(hz):g}")
        return out


class SpectrumPlot(pg.PlotWidget):
    """Live spectrum (dBFS over log frequency) filled in one colour; `ref` draws a faint comparison trace."""
    Y_MIN = -90

    def __init__(self, title: str, color_key: str, freqs: np.ndarray):
        super().__init__(axisItems={"bottom": FreqAxis("bottom")})
        self.color_key = color_key
        self.x = np.log10(np.maximum(freqs, 1.0))
        self.setXRange(np.log10(35), np.log10(20000), padding=0)
        self.setYRange(self.Y_MIN - 1.5, 2, padding=0)   # 0 and -90 labels stay visible
        self.getAxis("left").setTicks([[(v, str(v)) for v in range(0, self.Y_MIN - 1, -10)]])
        self.setMouseEnabled(False, False)
        self.hideButtons()
        self.setMenuEnabled(False)
        self.labels = ("Level (dBFS)", "Frequency (Hz)")
        self.ref = self.plot(self.x, np.full_like(self.x, -120))
        self.curve = self.plot(self.x, np.full_like(self.x, -120), fillLevel=self.Y_MIN)
        theme.notifier.changed.connect(self.apply_theme)
        self.apply_theme()

    def setTitle(self, title=None, **kw):     # the card above the plot shows the title
        pass

    def set_labels(self, left: str, bottom: str):
        self.labels = (left, bottom)
        self.apply_theme()

    def apply_theme(self):
        theme.style_plot(self, *self.labels)
        color = theme.tok(self.color_key)
        self.curve.setPen(pg.mkPen(color, width=1.8))
        self.curve.setBrush(pg.mkBrush(color + "50"))
        self.ref.setPen(pg.mkPen(theme.tok("axis") + "90", width=1))

    def set_data(self, db: np.ndarray, ref: np.ndarray | None = None):
        self.curve.setData(self.x, np.maximum(db, self.Y_MIN))
        if ref is not None:
            self.ref.setData(self.x, np.maximum(ref, self.Y_MIN))
