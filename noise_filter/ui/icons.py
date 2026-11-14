"""Small line icons drawn with QPainter (no image files, crisp at any DPI, any colour).

Every icon is drawn on a 24 x 24 grid. `pixmap()` renders one, `icon()` builds a QIcon with
an "off" and an "on" (selected tab / checked button) colour.
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui
from PySide6.QtCore import QPointF as P, QRectF as R

_DRAW = {}


def _icon(name):
    def deco(fn):
        _DRAW[name] = fn
        return fn
    return deco


def _poly(p, *pts, close=False):
    path = QtGui.QPainterPath(P(*pts[0]))
    for xy in pts[1:]:
        path.lineTo(P(*xy))
    if close:
        path.closeSubpath()
    p.drawPath(path)


def _fill(p, color):
    p.setBrush(QtGui.QColor(color))


@_icon("mic")
def _(p, c):
    p.drawRoundedRect(R(9, 3, 6, 11), 3, 3)
    p.drawArc(R(5, 4, 14, 14), 180 * 16, 180 * 16)
    _poly(p, (12, 18), (12, 21)); _poly(p, (9, 21), (15, 21))


@_icon("speaker")
def _(p, c):
    _poly(p, (4, 9.5), (8, 9.5), (12.5, 5.5), (12.5, 18.5), (8, 14.5), (4, 14.5), close=True)
    p.drawArc(R(11, 8.5, 7, 7), -55 * 16, 110 * 16)
    p.drawArc(R(10, 5, 11, 14), -55 * 16, 110 * 16)


@_icon("refresh")
def _(p, c):
    p.drawArc(R(5, 5, 14, 14), 30 * 16, 150 * 16)
    p.drawArc(R(5, 5, 14, 14), 210 * 16, 150 * 16)
    _poly(p, (18.6, 4.6), (18.1, 8.5), (14.3, 8.0))
    _poly(p, (5.4, 19.4), (5.9, 15.5), (9.7, 16.0))


@_icon("play")
def _(p, c):
    _fill(p, c); _poly(p, (8, 5.5), (18.5, 12), (8, 18.5), close=True)


@_icon("stop")
def _(p, c):
    _fill(p, c); p.drawRoundedRect(R(6.5, 6.5, 11, 11), 2, 2)


@_icon("wave")
def _(p, c):
    for x, h in zip(range(3, 22, 2), (3, 6, 11, 16, 8, 13, 18, 9, 5, 2)):
        _poly(p, (x, 12 - h / 2), (x, 12 + h / 2))


@_icon("sliders")
def _(p, c):
    for y, k in ((6, 15), (12, 8), (18, 13)):
        _poly(p, (3, y), (k - 2.4, y)); _poly(p, (k + 2.4, y), (21, y))
        p.drawEllipse(P(k, y), 2.4, 2.4)


@_icon("gauge")
def _(p, c):
    p.drawArc(R(3, 6, 18, 18), 0, 180 * 16)
    _poly(p, (12, 15), (16.5, 10.5))
    for a in (150, 115, 65, 30):
        r = math.radians(a)
        _poly(p, (12 + 7.2 * math.cos(r), 15 - 7.2 * math.sin(r)), (12 + 9 * math.cos(r), 15 - 9 * math.sin(r)))


@_icon("gear")
def _(p, c):
    pts = []
    for k in range(48):
        a = math.radians(k * 7.5 + 3.75)
        r = 9.3 if (k // 3) % 2 == 0 else 7.2
        pts.append((12 + r * math.cos(a), 12 + r * math.sin(a)))
    _poly(p, *pts, close=True)
    p.drawEllipse(P(12, 12), 3, 3)


@_icon("funnel")
def _(p, c):
    _poly(p, (3.5, 4.5), (20.5, 4.5), (14, 12.5), (14, 19), (10, 21), (10, 12.5), close=True)


@_icon("record")
def _(p, c):
    _fill(p, c); p.drawEllipse(P(12, 12), 6, 6)


@_icon("book")
def _(p, c):
    _poly(p, (12, 6.5), (12, 20))
    _poly(p, (12, 6.5), (8, 5), (3, 5), (3, 18), (8, 18), (12, 20), close=False)
    _poly(p, (12, 6.5), (16, 5), (21, 5), (21, 18), (16, 18), (12, 20), close=False)


@_icon("save")
def _(p, c):
    _poly(p, (4, 4), (17, 4), (20, 7), (20, 20), (4, 20), close=True)
    _poly(p, (8, 4), (8, 9), (15, 9), (15, 4))
    p.drawRect(R(7.5, 13, 9, 7))


@_icon("trash")
def _(p, c):
    _poly(p, (4, 7), (20, 7))
    _poly(p, (9, 7), (9, 4), (15, 4), (15, 7))
    _poly(p, (6, 7), (7.2, 20), (16.8, 20), (18, 7))
    _poly(p, (10, 10.5), (10, 16.5)); _poly(p, (14, 10.5), (14, 16.5))


@_icon("plus")
def _(p, c):
    _poly(p, (12, 5), (12, 19)); _poly(p, (5, 12), (19, 12))


@_icon("lock")
def _(p, c):
    path = QtGui.QPainterPath(P(8, 11)); path.lineTo(8, 8)
    path.arcTo(R(8, 4, 8, 8), 180, -180); path.lineTo(16, 11)
    p.drawPath(path)
    _fill(p, c); p.drawRoundedRect(R(5, 11, 14, 10), 2, 2)
    p.setPen(QtGui.QPen(QtGui.QColor("white"), 1.8, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap)); _poly(p, (12, 14.5), (12, 17))


@_icon("unlock")
def _(p, c):
    path = QtGui.QPainterPath(P(8, 11)); path.lineTo(8, 7)
    path.arcTo(R(8, 3, 8, 8), 180, -180); path.lineTo(16, 8)
    p.drawPath(path)
    p.drawRoundedRect(R(5, 11, 14, 10), 2, 2)
    _poly(p, (12, 14.5), (12, 17))


@_icon("compressor")
def _(p, c):
    p.drawArc(R(3, 7, 18, 18), 20 * 16, 140 * 16)
    _poly(p, (12, 4), (12, 11)); _poly(p, (9.5, 8.5), (12, 11), (14.5, 8.5))


@_icon("shield")
def _(p, c):
    path = QtGui.QPainterPath(P(12, 3))
    path.lineTo(19.5, 6); path.lineTo(19.5, 11)
    path.cubicTo(P(19.5, 16), P(16, 19.5), P(12, 21))
    path.cubicTo(P(8, 19.5), P(4.5, 16), P(4.5, 11))
    path.lineTo(4.5, 6); path.closeSubpath()
    p.drawPath(path)
    _poly(p, (8.8, 12), (11.2, 14.4), (15.4, 9.6))


@_icon("curve")
def _(p, c):
    _poly(p, (4, 20), (13, 11), (20, 8))
    p.drawEllipse(P(13, 11), 1.8, 1.8)
    p.drawEllipse(P(20, 8), 1.4, 1.4)


@_icon("power")
def _(p, c):
    p.drawArc(R(4.5, 5, 15, 15), 125 * 16, 290 * 16)
    _poly(p, (12, 3), (12, 11.5))


@_icon("layers")
def _(p, c):
    _poly(p, (12, 3.5), (21, 8), (12, 12.5), (3, 8), close=True)
    _poly(p, (3, 12), (12, 16.5), (21, 12))
    _poly(p, (3, 16), (12, 20.5), (21, 16))


@_icon("terminal")
def _(p, c):
    p.drawRoundedRect(R(3, 4, 18, 16), 2, 2)
    _poly(p, (7, 9), (10, 12), (7, 15)); _poly(p, (12.5, 15), (17, 15))


@_icon("copy")
def _(p, c):
    p.drawRoundedRect(R(8.5, 8.5, 11.5, 11.5), 2, 2)
    _poly(p, (15.5, 8.5), (15.5, 4), (4, 4), (4, 15.5), (8.5, 15.5))


@_icon("download")
def _(p, c):
    _poly(p, (12, 3.5), (12, 15)); _poly(p, (7.5, 10.5), (12, 15), (16.5, 10.5))
    _poly(p, (4, 15), (4, 20), (20, 20), (20, 15))


@_icon("upload")
def _(p, c):
    _poly(p, (12, 15), (12, 3.5)); _poly(p, (7.5, 8), (12, 3.5), (16.5, 8))
    _poly(p, (4, 15), (4, 20), (20, 20), (20, 15))


@_icon("sun")
def _(p, c):
    p.drawEllipse(P(12, 12), 4, 4)
    for k in range(8):
        a = math.radians(k * 45)
        _poly(p, (12 + 6.8 * math.cos(a), 12 + 6.8 * math.sin(a)), (12 + 9.2 * math.cos(a), 12 + 9.2 * math.sin(a)))


@_icon("moon")
def _(p, c):
    a = QtGui.QPainterPath(); a.addEllipse(P(12, 12), 8, 8)
    b = QtGui.QPainterPath(); b.addEllipse(P(17, 7), 7, 7)
    p.drawPath(a.subtracted(b))


@_icon("monitor")
def _(p, c):
    p.drawRoundedRect(R(3, 4, 18, 12), 2, 2)
    _poly(p, (12, 16), (12, 20)); _poly(p, (8, 20), (16, 20))


@_icon("info")
def _(p, c):
    p.drawEllipse(P(12, 12), 9, 9)
    _poly(p, (12, 11), (12, 16.5))
    _fill(p, c); p.drawEllipse(P(12, 7.6), 0.6, 0.6)


@_icon("chevron-down")
def _(p, c):
    _poly(p, (6, 9), (12, 15), (18, 9))


@_icon("chevron-up")
def _(p, c):
    _poly(p, (6, 15), (12, 9), (18, 15))


@_icon("check")
def _(p, c):
    _poly(p, (5, 12.5), (10, 17), (19, 7))


@_icon("dot")
def _(p, c):
    _fill(p, c); p.drawEllipse(P(12, 12), 5, 5)


NAMES = tuple(_DRAW)


def pixmap(name: str, color: str, size: int = 18, dpr: float = 2.0, width: float = 1.8) -> QtGui.QPixmap:
    px = QtGui.QPixmap(int(size * dpr), int(size * dpr))
    px.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(px)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    s = size * dpr / 24.0
    p.scale(s, s)
    p.setPen(QtGui.QPen(QtGui.QColor(color), width, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
    p.setBrush(QtCore.Qt.NoBrush)
    _DRAW[name](p, color)
    p.end()
    px.setDevicePixelRatio(dpr)
    return px


def icon(name: str, color: str, on_color: str | None = None, disabled: str | None = None,
         size: int = 18) -> QtGui.QIcon:
    ic = QtGui.QIcon()
    ic.addPixmap(pixmap(name, color, size), QtGui.QIcon.Normal, QtGui.QIcon.Off)
    ic.addPixmap(pixmap(name, on_color or color, size), QtGui.QIcon.Normal, QtGui.QIcon.On)
    ic.addPixmap(pixmap(name, on_color or color, size), QtGui.QIcon.Active, QtGui.QIcon.On)
    if disabled:
        ic.addPixmap(pixmap(name, disabled, size), QtGui.QIcon.Disabled, QtGui.QIcon.Off)
        ic.addPixmap(pixmap(name, disabled, size), QtGui.QIcon.Disabled, QtGui.QIcon.On)
    return ic
