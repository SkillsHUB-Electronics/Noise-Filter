"""Light / dark / system theme: colour tokens, the application style sheet and plot styling.

`apply(mode)` restyles the whole application; widgets that paint themselves (plots, switches,
meters) read `tok()` and listen to `notifier.changed`.
"""
from __future__ import annotations

import os
import tempfile

from PySide6 import QtCore, QtGui, QtWidgets as W

from . import icons

MODES = ("light", "dark", "system")

TOKENS = {
    "light": {
        "bg": "#eef3f9", "card": "#ffffff", "card_head": "#f6f9fd", "border": "#d6dfeb", "border_soft": "#e6ecf4",
        "text": "#1b2433", "muted": "#5d6878", "disabled": "#a3adbb",
        "accent": "#1a73e8", "accent_top": "#3b8ff0", "accent_hover": "#1565d0", "accent_soft": "#e3eefc",
        "input": "#ffffff", "input_border": "#c8d2df", "input_dis": "#f1f4f8",
        "btn": "#ffffff", "btn_hover": "#f1f6fd", "btn_press": "#e3eefc", "btn_dis": "#f4f6f9",
        "groove": "#d3dbe6", "handle": "#ffffff", "hover": "#e4ecf7",
        "green": "#1f9d55", "green_lit": "#22c55e", "amber": "#f59e0b", "red": "#e5484d",
        "warn": "#f59e0b", "warn_soft": "#fff4e0", "info_bg": "#eef5ff", "info_border": "#cfe0fb",
        "plot_bg": "#ffffff", "axis": "#9aa6b5", "grid": 70, "meter_off": "#dfe5ee",
        "spec_in": "#1a73e8", "spec_out": "#1fb85a",
    },
    "dark": {
        "bg": "#14181e", "card": "#1d232b", "card_head": "#222932", "border": "#2f3843", "border_soft": "#29313b",
        "text": "#e6ebf2", "muted": "#9aa5b4", "disabled": "#5f6a78",
        "accent": "#3b8cf0", "accent_top": "#5aa2f5", "accent_hover": "#5aa2f5", "accent_soft": "#1f3350",
        "input": "#252c35", "input_border": "#3a4452", "input_dis": "#20262e",
        "btn": "#262e38", "btn_hover": "#2e3844", "btn_press": "#1f3350", "btn_dis": "#21272f",
        "groove": "#3a4452", "handle": "#e6ebf2", "hover": "#27303b",
        "green": "#3dd68c", "green_lit": "#3dd68c", "amber": "#f5b041", "red": "#f2555a",
        "warn": "#f5a524", "warn_soft": "#3a2e17", "info_bg": "#1b2a3f", "info_border": "#2b4466",
        "plot_bg": "#1d232b", "axis": "#6c7887", "grid": 55, "meter_off": "#323b47",
        "spec_in": "#4ea1ff", "spec_out": "#3dd68c",
    },
}


class _Notifier(QtCore.QObject):
    changed = QtCore.Signal()


notifier = _Notifier()
_state = {"mode": "light", "name": "light", "dir": None, "hooked": False}


def tok(key: str | None = None):
    t = TOKENS[_state["name"]]
    return t if key is None else t[key]


def name() -> str:
    return _state["name"]


def mode() -> str:
    return _state["mode"]


def resolve(mode: str) -> str:
    if mode in ("light", "dark"):
        return mode
    try:
        scheme = QtGui.QGuiApplication.styleHints().colorScheme()
        return "dark" if scheme == QtCore.Qt.ColorScheme.Dark else "light"
    except Exception:          # Qt older than 6.5
        return "light"


def _assets(t: dict) -> dict:
    """Arrow and check images the style sheet needs (written once per theme to a temp folder)."""
    if _state["dir"] is None:
        _state["dir"] = tempfile.mkdtemp(prefix="nf-theme-")
    out = {}
    for key, icon_name, color in (("down", "chevron-down", t["muted"]), ("up", "chevron-up", t["muted"]),
                                  ("down_dis", "chevron-down", t["disabled"]), ("up_dis", "chevron-up", t["disabled"]),
                                  ("check", "check", "#ffffff"), ("check_acc", "check", t["accent"])):
        path = os.path.join(_state["dir"], f"{_state['name']}-{key}.png")
        if not os.path.exists(path):
            icons.pixmap(icon_name, color, 16, dpr=2.0, width=2.6 if "check" in key else 2.2).save(path)
        out[key] = path.replace("\\", "/")
    return out


def stylesheet(t: dict) -> str:
    a = _assets(t)
    return f"""
QMainWindow, QDialog {{ background: {t['bg']}; }}
QWidget {{ color: {t['text']}; }}
QWidget#page, QWidget#scrollPage {{ background: transparent; }}
QToolTip {{ background: {t['card']}; color: {t['text']}; border: 1px solid {t['border']}; padding: 4px; }}
QLabel#appTitle {{ font-size: 15pt; font-weight: 700; }}
QLabel#appSubtitle, QLabel#muted, QLabel#note {{ color: {t['muted']}; }}
QLabel#sectionLabel {{ color: {t['text']}; font-weight: 600; }}
QLabel#cardTitle {{ font-size: 11pt; font-weight: 700; }}
QLabel#strong, QCheckBox#strong {{ font-weight: 600; }}
QLabel#value {{ font-weight: 600; }}
QFrame#card {{ background: {t['card']}; border: 1px solid {t['border']}; border-radius: 10px; }}
QWidget#cardHeader {{ background: {t['card_head']}; border: none; border-bottom: 1px solid {t['border_soft']};
    border-top-left-radius: 10px; border-top-right-radius: 10px; }}
QFrame#vline {{ background: {t['border']}; border: none; max-width: 1px; min-width: 1px; }}
QFrame#infoBanner {{ background: {t['info_bg']}; border: 1px solid {t['info_border']}; border-radius: 6px; }}
QFrame#statusBar {{ background: {t['card']}; border: 1px solid {t['border']}; border-radius: 10px; }}
QFrame#pill {{ background: {t['card']}; border: 1px solid {t['border']}; border-radius: 8px; }}
QLabel#statusSep {{ color: {t['border']}; }}

QPushButton, QToolButton#btn {{ background: {t['btn']}; border: 1px solid {t['border']}; border-radius: 6px;
    padding: 5px 12px; }}
QPushButton:hover, QToolButton#btn:hover {{ background: {t['btn_hover']}; border-color: {t['accent']}; }}
QPushButton:pressed, QToolButton#btn:pressed {{ background: {t['btn_press']}; }}
QPushButton:disabled, QToolButton#btn:disabled {{ color: {t['disabled']}; background: {t['btn_dis']};
    border-color: {t['border_soft']}; }}
QPushButton#primary {{ color: white; border: none; border-radius: 8px; font-size: 12pt; font-weight: 700;
    padding: 8px 22px; background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {t['accent_top']}, stop:1 {t['accent']}); }}
QPushButton#primary:hover {{ background: {t['accent_hover']}; }}
QPushButton#primary:disabled {{ background: {t['groove']}; color: {t['muted']}; }}
QPushButton#lockBtn:checked {{ background: {t['warn_soft']}; border-color: {t['warn']}; }}
QPushButton[seg="true"] {{ border-radius: 0px; padding: 6px 18px; min-width: 80px; }}
QPushButton[seg="true"][pos="first"] {{ border-top-left-radius: 6px; border-bottom-left-radius: 6px; }}
QPushButton[seg="true"][pos="last"] {{ border-top-right-radius: 6px; border-bottom-right-radius: 6px; }}
QPushButton[seg="true"]:checked {{ color: white; border-color: {t['accent']};
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {t['accent_top']}, stop:1 {t['accent']}); }}
QToolButton#cellBtn {{ background: transparent; border: none; border-radius: 4px; padding: 2px; }}
QToolButton#cellBtn:hover {{ background: {t['hover']}; }}
QToolButton#cellBtn:disabled {{ background: transparent; }}

QComboBox, QAbstractSpinBox, QLineEdit, QToolButton#comboLike {{ background: {t['input']}; border: 1px solid {t['input_border']};
    border-radius: 6px; padding: 3px 8px; min-height: 20px; }}
QComboBox:hover, QAbstractSpinBox:hover, QLineEdit:hover, QToolButton#comboLike:hover {{ border-color: {t['accent']}; }}
QComboBox:focus, QAbstractSpinBox:focus, QLineEdit:focus {{ border-color: {t['accent']}; }}
QComboBox:disabled, QAbstractSpinBox:disabled, QLineEdit:disabled, QToolButton#comboLike:disabled {{
    background: {t['input_dis']}; color: {t['disabled']}; border-color: {t['border_soft']}; }}
QAbstractSpinBox[locked="true"] {{ background: {t['input_dis']}; padding-right: 8px; }}
QAbstractSpinBox[locked="true"]::up-button, QAbstractSpinBox[locked="true"]::down-button {{ width: 0px; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url({a['down']}); width: 12px; height: 12px; }}
QComboBox::down-arrow:disabled {{ image: url({a['down_dis']}); }}
QToolButton#comboLike {{ text-align: left; padding-right: 26px; }}
QToolButton#comboLike::menu-indicator {{ image: url({a['down']}); width: 12px; height: 12px;
    subcontrol-origin: padding; subcontrol-position: center right; right: 8px; }}
QComboBox QAbstractItemView {{ background: {t['card']}; border: 1px solid {t['border']}; outline: 0;
    selection-background-color: {t['accent_soft']}; selection-color: {t['text']}; }}
QAbstractSpinBox {{ padding-right: 20px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ subcontrol-origin: border; width: 18px;
    border: none; background: transparent; }}
QAbstractSpinBox::up-button {{ subcontrol-position: top right; margin-top: 2px; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; margin-bottom: 2px; }}
QAbstractSpinBox::up-arrow {{ image: url({a['up']}); width: 10px; height: 10px; }}
QAbstractSpinBox::down-arrow {{ image: url({a['down']}); width: 10px; height: 10px; }}
QAbstractSpinBox::up-arrow:disabled, QAbstractSpinBox::up-arrow:off {{ image: url({a['up_dis']}); }}
QAbstractSpinBox::down-arrow:disabled, QAbstractSpinBox::down-arrow:off {{ image: url({a['down_dis']}); }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {t['input_border']}; border-radius: 4px;
    background: {t['input']}; }}
QCheckBox::indicator:hover {{ border-color: {t['accent']}; }}
QCheckBox::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']}; image: url({a['check']}); }}
QCheckBox::indicator:disabled {{ background: {t['input_dis']}; border-color: {t['border_soft']}; }}
QCheckBox::indicator:checked:disabled {{ background: {t['disabled']}; }}
QCheckBox:disabled {{ color: {t['disabled']}; }}

QSlider {{ min-height: 20px; }}
QSlider::groove:horizontal {{ height: 4px; background: {t['groove']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {t['handle']}; border: 3px solid {t['accent']}; width: 10px; height: 10px;
    margin: -6px 0; border-radius: 8px; }}
QSlider::handle:horizontal:hover {{ border-color: {t['accent_hover']}; }}
QSlider::sub-page:horizontal:disabled {{ background: {t['disabled']}; }}
QSlider::handle:horizontal:disabled {{ border-color: {t['disabled']}; }}

QTabWidget::pane {{ border: none; border-top: 1px solid {t['border']}; top: -1px; }}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{ background: transparent; border: none; padding: 7px 16px; margin: 0 4px 7px 0; border-radius: 8px;
    color: {t['text']}; font-weight: 600; font-size: 10pt; }}
QTabBar::tab:hover {{ background: {t['hover']}; }}
QTabBar::tab:selected {{ color: white;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {t['accent_top']}, stop:1 {t['accent']}); }}

QTableWidget {{ background: {t['card']}; border: none; gridline-color: transparent;
    selection-background-color: {t['accent_soft']}; selection-color: {t['text']}; }}
QTableWidget::item {{ border-bottom: 1px solid {t['border_soft']}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {t['card_head']}; color: {t['text']}; border: none;
    border-bottom: 1px solid {t['border']}; padding: 5px 4px; font-weight: 600; }}
QTableCornerButton::section {{ background: {t['card_head']}; border: none; }}

QProgressBar#thinBar {{ background: {t['groove']}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }}
QProgressBar#thinBar::chunk {{ background: {t['accent']}; border-radius: 3px; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t['groove']}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {t['disabled']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t['groove']}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMenu {{ background: {t['card']}; border: 1px solid {t['border']}; padding: 4px; }}
QMenu::item {{ padding: 5px 24px 5px 28px; border-radius: 4px; }}
QMenu::item:selected {{ background: {t['accent_soft']}; color: {t['text']}; }}
QMenu::item:disabled {{ color: {t['disabled']}; }}
QMenu::separator {{ height: 1px; background: {t['border_soft']}; margin: 4px 8px; }}
QMenu::indicator {{ width: 14px; height: 14px; left: 8px; }}
QMenu::indicator:checked {{ image: url({a['check_acc']}); }}
QMessageBox, QInputDialog {{ background: {t['bg']}; }}
"""


def _palette(t: dict) -> QtGui.QPalette:
    pal = QtGui.QPalette()
    C = QtGui.QColor
    for role, key in ((QtGui.QPalette.Window, "bg"), (QtGui.QPalette.WindowText, "text"), (QtGui.QPalette.Base, "input"),
                      (QtGui.QPalette.AlternateBase, "card_head"), (QtGui.QPalette.Text, "text"),
                      (QtGui.QPalette.Button, "btn"), (QtGui.QPalette.ButtonText, "text"),
                      (QtGui.QPalette.ToolTipBase, "card"), (QtGui.QPalette.ToolTipText, "text"),
                      (QtGui.QPalette.Highlight, "accent"), (QtGui.QPalette.PlaceholderText, "muted"),
                      (QtGui.QPalette.Link, "accent"), (QtGui.QPalette.Mid, "border"), (QtGui.QPalette.Light, "card")):
        pal.setColor(role, C(t[key]))
    pal.setColor(QtGui.QPalette.HighlightedText, C("#ffffff"))
    for role in (QtGui.QPalette.WindowText, QtGui.QPalette.Text, QtGui.QPalette.ButtonText):
        pal.setColor(QtGui.QPalette.Disabled, role, C(t["disabled"]))
    return pal


def apply(mode: str = "light") -> None:
    app = W.QApplication.instance()
    if app is None:
        return
    mode = mode if mode in MODES else "light"
    _state["mode"], _state["name"] = mode, resolve(mode)
    t = tok()
    if app.style().name().lower() != "fusion":
        app.setStyle("Fusion")
    app.setPalette(_palette(t))
    app.setStyleSheet(stylesheet(t))
    if not _state["hooked"]:
        _state["hooked"] = True
        try:   # follow Windows when the theme is "System"
            QtGui.QGuiApplication.styleHints().colorSchemeChanged.connect(
                lambda *_: apply(_state["mode"]) if _state["mode"] == "system" else None)
        except Exception:
            pass
    notifier.changed.emit()


def style_plot(pw, left: str = "", bottom: str = "") -> None:
    """Theme a pyqtgraph PlotWidget: background, axes, grid and axis titles."""
    import pyqtgraph as pg
    t = tok()
    pw.setBackground(t["plot_bg"])
    font = QtGui.QFont(); font.setPointSizeF(8.5)
    for side in ("left", "bottom"):
        ax = pw.getAxis(side)
        ax.setPen(pg.mkPen(t["axis"], width=1))
        ax.setTextPen(pg.mkPen(t["muted"]))
        ax.setStyle(tickFont=font, tickLength=-4)
        ax.setGrid(t["grid"])
    if left:
        pw.setLabel("left", left, color=t["muted"], **{"font-size": "9pt"})
    if bottom:
        pw.setLabel("bottom", bottom, color=t["muted"], **{"font-size": "9pt"})
