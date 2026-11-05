import numpy as np
import pyqtgraph as pg

TICKS = [50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]


class FreqAxis(pg.AxisItem):
    """Log-frequency axis: data x is log10(Hz); labels show Hz / kHz."""

    def tickValues(self, minVal, maxVal, size):
        return [(1.0, [np.log10(t) for t in TICKS if minVal <= np.log10(t) <= maxVal])]

    def tickStrings(self, values, scale, spacing):
        out = []
        for v in values:
            hz = 10 ** v
            out.append(f"{hz / 1000:g}k" if hz >= 1000 else f"{hz:g}")
        return out


class SpectrumPlot(pg.PlotWidget):
    def __init__(self, title: str, color: str, freqs: np.ndarray):
        super().__init__(axisItems={"bottom": FreqAxis("bottom")})
        self.setBackground(None)
        self.x = np.log10(np.maximum(freqs, 1.0))
        self.setXRange(np.log10(30), np.log10(20000), padding=0)
        self.setYRange(-100, 0, padding=0)
        self.setMouseEnabled(False, False)
        self.showGrid(x=True, y=True, alpha=0.25)
        self.setLabel("left", "dBFS")
        self.setLabel("bottom", "Hz")
        self.setTitle(title)
        self.curve = self.plot(self.x, np.full_like(self.x, -120), pen=pg.mkPen(color, width=2),
                               fillLevel=-100, brush=pg.mkBrush(color + "40"))
        # faint reference trace (e.g. input drawn behind output for comparison)
        self.ref = self.plot(self.x, np.full_like(self.x, -120), pen=pg.mkPen("#888888", width=1))

    def set_data(self, db: np.ndarray, ref: np.ndarray | None = None):
        self.curve.setData(self.x, db)
        if ref is not None:
            self.ref.setData(self.x, ref)
