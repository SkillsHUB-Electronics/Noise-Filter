"""'Help the AI get better?' card shown after Learn noise, when the recording passed screening."""
from __future__ import annotations

import numpy as np
from PySide6 import QtCore, QtWidgets as W

from .. import contribute
from ..i18n import tr


class ContributeDialog(W.QDialog):
    """Returns Accepted with .category set when the user chose to send; .never is True when the
    user asked not to be asked again."""

    def __init__(self, sample: np.ndarray, lang: str, parent=None):
        super().__init__(parent)
        self.sample, self.lang, self.never, self.category = sample, lang, False, None
        t = lambda k: tr(k, lang)
        self.setWindowTitle(t("contrib.title"))
        lay = W.QVBoxLayout(self)
        msg = W.QLabel(t("contrib.body").format(s=len(sample) / contribute.SR))
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

        btns = W.QHBoxLayout()
        self.send_btn = W.QPushButton(t("contrib.send"))
        self.send_btn.setDefault(True)
        self.later_btn = W.QPushButton(t("contrib.later"))
        self.never_btn = W.QPushButton(t("contrib.never"))
        self.send_btn.clicked.connect(self._send)
        self.later_btn.clicked.connect(self.reject)
        self.never_btn.clicked.connect(self._never)
        btns.addWidget(self.never_btn); btns.addStretch(1); btns.addWidget(self.later_btn); btns.addWidget(self.send_btn)
        lay.addLayout(btns)
        self.consent.toggled.connect(self.send_btn.setEnabled)
        self.send_btn.setEnabled(self.consent.isChecked())

    def _play(self):
        try:
            import sounddevice as sd
            sd.play(self.sample, contribute.SR)
        except Exception:
            self.play_btn.setEnabled(False)

    def _send(self):
        if not self.consent.isChecked():
            return
        contribute.save_state(consent=contribute.CONSENT)
        self.category = self.cat.currentData()
        self.accept()

    def _never(self):
        self.never = True
        contribute.save_state(ask=False)
        self.reject()


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
