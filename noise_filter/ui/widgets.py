"""Building blocks of the v0.8 look: cards, switches, a segmented level meter, icon buttons."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets as W

from . import icons, theme


class Card(W.QFrame):
    """Rounded panel with a tinted header (icon + title + optional widgets on the right).
    `title()` / `setTitle()` behave like QGroupBox ("&&" shows as "&")."""

    def __init__(self, icon_name: str | None = None, parent=None, icon_color: str | None = None):
        super().__init__(parent)
        self.setObjectName("card")
        self._title = ""
        self._icon_name, self._icon_color = icon_name, icon_color
        outer = W.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.header = W.QWidget(); self.header.setObjectName("cardHeader")
        self.header.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        h = W.QHBoxLayout(self.header)
        h.setContentsMargins(14, 7, 12, 7)
        h.setSpacing(8)
        self.icon_lbl = W.QLabel()
        self.title_lbl = W.QLabel(); self.title_lbl.setObjectName("cardTitle")
        h.addWidget(self.icon_lbl); h.addWidget(self.title_lbl); h.addStretch(1)
        self.header_lay = h
        outer.addWidget(self.header)
        self.body = W.QWidget()
        outer.addWidget(self.body, 1)
        self.icon_lbl.setVisible(bool(icon_name))
        theme.notifier.changed.connect(self._restyle)
        self._restyle()

    def setBodyLayout(self, lay: W.QLayout, margins=(14, 10, 14, 12)):
        lay.setContentsMargins(*margins)
        self.body.setLayout(lay)
        return lay

    def addHeaderWidget(self, w: W.QWidget):
        self.header_lay.addWidget(w)

    def title(self) -> str:
        return self._title

    def setTitle(self, text: str):
        self._title = text
        self.title_lbl.setText(text.replace("&&", "&"))

    def setIconColor(self, color: str | None):
        self._icon_color = color
        self._restyle()

    def _restyle(self):
        if self._icon_name:
            self.icon_lbl.setPixmap(icons.pixmap(self._icon_name, self._icon_color or theme.tok("accent"), 20))


def vline() -> W.QFrame:
    f = W.QFrame(); f.setObjectName("vline"); f.setFixedWidth(1)
    return f


def scroll_page(widget: W.QWidget) -> W.QScrollArea:
    """Wrap a tab page so small laptop screens can scroll instead of squashing it."""
    widget.setObjectName("scrollPage")
    sa = W.QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(W.QFrame.NoFrame)
    sa.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
    sa.setWidget(widget)
    sa.viewport().setAutoFillBackground(False)
    widget.setAutoFillBackground(False)
    return sa


class IconButton:
    """Keeps a button's icon in the theme colours: set_icon(button, name)."""
    _buttons: list = []

    @classmethod
    def set(cls, btn: W.QAbstractButton, name: str, color_key: str = "text", on_key: str | None = None, size: int = 16):
        btn._nf_icon = (name, color_key, on_key, size)
        btn.setIconSize(QtCore.QSize(size, size))
        cls._apply(btn)
        if btn not in cls._buttons:
            cls._buttons.append(btn)
            btn.destroyed.connect(lambda *_, b=btn: cls._buttons.remove(b) if b in cls._buttons else None)

    @classmethod
    def _apply(cls, btn):
        name, ck, ok, size = btn._nf_icon
        t = theme.tok()
        col = t.get(ck, ck)
        btn.setIcon(icons.icon(name, col, t.get(ok, ok) if ok else None, t["disabled"], size))

    @classmethod
    def restyle_all(cls):
        for b in list(cls._buttons):
            try:
                cls._apply(b)
            except RuntimeError:          # deleted on the C++ side
                cls._buttons.remove(b)


theme.notifier.changed.connect(IconButton.restyle_all)


class ToggleSwitch(W.QCheckBox):
    """On/off switch (a QCheckBox underneath, so checked/toggled work as before)."""
    TRACK_W, TRACK_H = 38, 20

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        theme.notifier.changed.connect(self.update)

    def sizeHint(self):
        fm = self.fontMetrics()
        w = self.TRACK_W + 4 + (10 + fm.horizontalAdvance(self.text()) if self.text() else 0)
        return QtCore.QSize(w, max(self.TRACK_H + 4, fm.height() + 6))

    def minimumSizeHint(self):
        return self.sizeHint()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _):
        t = theme.tok()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        on, en = self.isChecked(), self.isEnabled()
        y = (self.height() - self.TRACK_H) / 2
        track = QtCore.QRectF(1, y, self.TRACK_W, self.TRACK_H)
        if on:
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(t["accent"] if en else t["disabled"]))
        else:
            p.setPen(QtGui.QPen(QtGui.QColor(t["input_border"]), 1))
            p.setBrush(QtGui.QColor(t["input_dis"]))
        p.drawRoundedRect(track, self.TRACK_H / 2, self.TRACK_H / 2)
        d = self.TRACK_H - 6
        x = track.right() - d - 3 if on else track.left() + 3
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor("#ffffff" if on else (t["muted"] if en else t["disabled"])))
        p.drawEllipse(QtCore.QRectF(x, y + 3, d, d))
        if self.text():
            p.setPen(QtGui.QColor(t["text"] if en else t["disabled"]))
            r = QtCore.QRectF(self.TRACK_W + 12, 0, self.width() - self.TRACK_W - 12, self.height())
            p.drawText(r, QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, self.text())
        p.end()


class LevelMeter(W.QWidget):
    """Segmented level meter (-60..0 dBFS): green, then amber and red near full scale."""
    SEGMENTS = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db = -120.0
        self.setFixedHeight(18)
        self.setMinimumWidth(120)
        theme.notifier.changed.connect(self.update)

    def setLevel(self, db: float):
        db = float(db)
        if abs(db - self._db) > 0.25:
            self._db = db
            self.update()

    def level(self) -> float:
        return self._db

    def sizeHint(self):
        return QtCore.QSize(150, 18)

    def paintEvent(self, _):
        t = theme.tok()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        n = self.SEGMENTS
        gap = 2.0
        w = (self.width() - gap * (n - 1)) / n
        lit = int(round((min(0.0, max(-60.0, self._db)) + 60.0) / 60.0 * n)) if self._db > -60 else 0
        p.setPen(QtCore.Qt.NoPen)
        for i in range(n):
            if i < lit:
                col = t["red"] if i >= n - 2 else t["amber"] if i >= n - 4 else t["green_lit"]
            else:
                col = t["meter_off"]
            p.setBrush(QtGui.QColor(col))
            p.drawRoundedRect(QtCore.QRectF(i * (w + gap), 0, w, self.height()), 1.5, 1.5)
        p.end()


class StatusDot(W.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = "#22c55e"
        self.setFixedSize(14, 14)

    def setColor(self, c: str):
        self._color = c
        self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        c = QtGui.QColor(self._color)
        p.setPen(QtGui.QPen(c, 2.4))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawEllipse(QtCore.QRectF(2, 2, 10, 10))
        p.setPen(QtCore.Qt.NoPen); p.setBrush(c)
        p.drawEllipse(QtCore.QRectF(4.5, 4.5, 5, 5))
        p.end()


class ColorDot(W.QWidget):
    def __init__(self, color: str, size: int = 10, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(size, size)

    def setColor(self, c: str):
        self._color = c
        self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtCore.Qt.NoPen); p.setBrush(QtGui.QColor(self._color))
        p.drawEllipse(self.rect().adjusted(0, 0, -1, -1))
        p.end()


class BandCheck(W.QCheckBox):
    """EQ table: the band's on/off tick plus its coloured number badge."""

    def __init__(self, number: int, color: str, parent=None):
        super().__init__(parent)
        self.number, self.color = number, color
        self.setCursor(QtCore.Qt.PointingHandCursor)

    def sizeHint(self):
        return QtCore.QSize(62, 26)

    def minimumSizeHint(self):
        return self.sizeHint()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _):
        t = theme.tok()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        en, on = self.isEnabled(), self.isChecked()
        cy = self.height() / 2
        box = QtCore.QRectF(8, cy - 8, 16, 16)
        if on:
            p.setPen(QtCore.Qt.NoPen); p.setBrush(QtGui.QColor(t["accent"] if en else t["disabled"]))
        else:
            p.setPen(QtGui.QPen(QtGui.QColor(t["input_border"]), 1)); p.setBrush(QtGui.QColor(t["input"]))
        p.drawRoundedRect(box, 4, 4)
        if on:
            p.setPen(QtGui.QPen(QtGui.QColor("white"), 2, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
            path = QtGui.QPainterPath(QtCore.QPointF(11.5, cy + 0.5))
            path.lineTo(14.8, cy + 3.6); path.lineTo(20.5, cy - 3.2)
            p.setBrush(QtCore.Qt.NoBrush); p.drawPath(path)
        c = QtGui.QColor(self.color)
        if not on:
            c.setAlphaF(0.45)
        p.setPen(QtCore.Qt.NoPen); p.setBrush(c)
        badge = QtCore.QRectF(32, cy - 10, 20, 20)
        p.drawEllipse(badge)
        f = p.font(); f.setBold(True); p.setFont(f)
        p.setPen(QtGui.QColor("white"))
        p.drawText(badge, QtCore.Qt.AlignCenter, str(self.number))
        p.end()


class InfoBanner(W.QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("infoBanner")
        lay = W.QHBoxLayout(self)
        lay.setContentsMargins(10, 5, 10, 5)
        lay.setSpacing(8)
        self.icon = W.QLabel()
        self.label = W.QLabel(); self.label.setWordWrap(True)
        lay.addWidget(self.icon, 0, QtCore.Qt.AlignTop); lay.addWidget(self.label, 1)
        theme.notifier.changed.connect(self._restyle)
        self._restyle()

    def setText(self, text):
        self.label.setText(text)

    def text(self):
        return self.label.text()

    def _restyle(self):
        self.icon.setPixmap(icons.pixmap("info", theme.tok("accent"), 16))
