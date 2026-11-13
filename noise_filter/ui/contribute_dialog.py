"""'Help the AI get better?' card shown after Learn noise, when the recording passed screening,
and after the user picked an audio file of their own (file=dict(name, clips, dropped))."""
from __future__ import annotations

import numpy as np
from PySide6 import QtCore, QtWidgets as W

from .. import contribute
from ..i18n import tr


class ContributeDialog(W.QDialog):
    """Returns Accepted with .category set when the user chose to send; .never is True when the
    user asked not to be asked again."""

    def __init__(self, sample: np.ndarray, lang: str, parent=None, file: dict | None = None):
        super().__init__(parent)
        self.sample, self.lang, self.never, self.category = sample, lang, False, None
        t = lambda k: tr(k, lang)
        self.setWindowTitle(t("contrib.title"))
        lay = W.QVBoxLayout(self)
        if file:
            text = t("contrib.file_body").format(name=file["name"], n=file["clips"], s=len(sample) / contribute.SR)
            if file.get("dropped"):
                text += " " + t("contrib.file_dropped").format(n=file["dropped"])
        else:
            text = t("contrib.body").format(s=len(sample) / contribute.SR)
        msg = W.QLabel(text)
        msg.setWordWrap(True)
        lay.addWidget(msg)

        row = W.QHBoxLayout()
        self.play_btn = W.QPushButton(t("contrib.play"))
        self.play_btn.clicked.connect(self._play)
        self.cat = W.QComboBox()
        for c in contribute.CATEGORIES:
            self.cat.addItem(t(f"contrib.cat.{c}"), c)
        row.addWidget(self.play_btn); row.addWidget(W.QLabel(t("contrib.category"))); row.addWidget(self.cat, 1)
        lay.addLayout(row)

        self.consent = W.QCheckBox(t("contrib.consent"))
        self.consent.setStyleSheet("QCheckBox { font-size: 11px; }")
        already = contribute.load_state().get("consent") == contribute.CONSENT
        self.consent.setChecked(already)
        self.consent.setVisible(not already)
        lay.addWidget(self.consent)
        # a file could come from anywhere: the user confirms every time that they recorded it
        self.own = W.QCheckBox(t("contrib.own_recording"))
        self.own.setStyleSheet("QCheckBox { font-size: 11px; }")
        self.own.setChecked(not file)
        self.own.setVisible(bool(file))
        lay.addWidget(self.own)

        btns = W.QHBoxLayout()
        self.send_btn = W.QPushButton(t("contrib.send"))
        self.send_btn.setDefault(True)
        self.later_btn = W.QPushButton(t("contrib.later"))
        self.never_btn = W.QPushButton(t("contrib.never"))
        self.send_btn.clicked.connect(self._send)
        self.later_btn.clicked.connect(self.reject)
        self.never_btn.clicked.connect(self._never)
        btns.addWidget(self.never_btn); btns.addStretch(1); btns.addWidget(self.later_btn); btns.addWidget(self.send_btn)
        self.never_btn.setVisible(not file)
        lay.addLayout(btns)
        for cb in (self.consent, self.own):
            cb.toggled.connect(self._update_send)
        self._update_send()

    def _update_send(self, *_):
        self.send_btn.setEnabled(self.consent.isChecked() and self.own.isChecked())

    def _play(self):
        try:
            import sounddevice as sd
            sd.play(self.sample, contribute.SR)
        except Exception:
            self.play_btn.setEnabled(False)

    def _send(self):
        if not (self.consent.isChecked() and self.own.isChecked()):
            return
        contribute.save_state(consent=contribute.CONSENT)
        self.category = self.cat.currentData()
        self.accept()

    def _never(self):
        self.never = True
        contribute.save_state(ask=False)
        self.reject()


class RecordDialog(W.QDialog):
    """'Record noise': records the raw microphone input through the running pipeline for a few
    seconds with a countdown and a level meter. After exec(): .raw / .dropped (Accepted) or
    nothing (Rejected = cancelled)."""

    def __init__(self, pipe, lang: str, parent=None, seconds: float | None = None):
        super().__init__(parent)
        t = lambda k: tr(k, lang)
        self.pipe, self.raw, self.dropped = pipe, None, 0
        self.total = float(seconds if seconds is not None else contribute.TRIM_START + contribute.RECORD_SECONDS)
        self.setWindowTitle(t("contrib.record_title"))
        self.setMinimumWidth(380)
        lay = W.QVBoxLayout(self)
        tip = W.QLabel(t("contrib.record_tip"))
        tip.setWordWrap(True)
        lay.addWidget(tip)
        self.left = W.QLabel()
        f = self.left.font(); f.setPointSize(f.pointSize() + 8); f.setBold(True); self.left.setFont(f)
        self.left.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(self.left)
        self.progress = W.QProgressBar(); self.progress.setRange(0, 1000); self.progress.setTextVisible(False)
        self.level = W.QProgressBar(); self.level.setRange(-80, 0); self.level.setTextVisible(False)
        self.level.setMaximumHeight(8)
        lay.addWidget(self.progress); lay.addWidget(self.level)
        row = W.QHBoxLayout(); row.addStretch(1)
        cancel = W.QPushButton(t("contrib.record_cancel")); cancel.clicked.connect(self.reject)
        row.addWidget(cancel); lay.addLayout(row)
        self._t0 = None
        self._timer = QtCore.QTimer(self, interval=50, timeout=self._tick)
        self._fmt = t("contrib.record_left")

    def showEvent(self, e):
        super().showEvent(e)
        if self._t0 is None:
            import time
            self._now = time.monotonic
            self._t0 = self._now()
            self.pipe.capture_start(int(self.total * contribute.SR))
            self._timer.start()
            self._tick()

    def _tick(self):
        el = self._now() - self._t0
        self.progress.setValue(int(min(1.0, el / self.total) * 1000))
        self.left.setText(self._fmt.format(s=max(0, int(self.total - el + 0.999))))
        try:
            self.level.setValue(int(max(-80, min(0, self.pipe.in_analyzer.level_db()))))
        except Exception:
            pass
        if el >= self.total:
            self._timer.stop()
            self.raw, self.dropped = self.pipe.capture_stop()
            self.accept()

    def reject(self):
        if self._timer.isActive():
            self._timer.stop()
            self.pipe.capture_stop()
        super().reject()


class UploadWorker(QtCore.QObject):
    """Runs upload / delete off the UI thread; `done(ok, message)` arrives on the UI thread."""
    done = QtCore.Signal(bool, str)

    def run(self, fn, *args):
        import threading

        def work():
            try:
                self.done.emit(True, str(fn(*args)))
            except Exception as e:  # offline, service down, rejected
                self.done.emit(False, str(e))
        threading.Thread(target=work, daemon=True, name="contribute").start()
