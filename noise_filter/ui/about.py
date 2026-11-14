"""About card for the Settings tab and a viewer for the license, privacy policy and third-party notices."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets as W

from .. import __version__, legal, model_update
from ..i18n import tr
from .widgets import Card, IconButton


class DocDialog(W.QDialog):
    """Shows one of the bundled legal documents (Markdown or plain text). Web links open in the browser;
    links between the documents (e.g. to the Indonesian privacy policy) switch the document in place."""

    def __init__(self, doc: str, lang: str, parent=None):
        super().__init__(parent)
        self.lang = lang
        self.resize(720, 620)
        lay = W.QVBoxLayout(self)
        self.view = W.QTextBrowser()
        self.view.setOpenLinks(False)
        self.view.anchorClicked.connect(self._link)
        lay.addWidget(self.view, 1)
        row = W.QHBoxLayout(); row.addStretch(1)
        close = W.QPushButton(tr("about.close", lang)); close.clicked.connect(self.accept); close.setDefault(True)
        row.addWidget(close)
        lay.addLayout(row)
        self.show_doc(doc, lang)

    def show_doc(self, doc: str, lang: str):
        self.doc = doc
        self.setWindowTitle(f"{tr('app.title', self.lang)} - {tr(f'about.{doc}', self.lang)}")
        body = legal.text(doc, lang)
        if legal.file_name(doc, lang).endswith(".md"):
            self.view.setMarkdown(body)
        else:
            self.view.setPlainText(body)
        self.view.moveCursor(QtGui.QTextCursor.Start)

    def _link(self, url: QtCore.QUrl):
        if url.scheme() in ("http", "https", "mailto"):
            QtGui.QDesktopServices.openUrl(url)
            return
        target = legal.doc_for_file(url.toString())
        if target:
            self.show_doc(*target)


def show_doc(doc: str, lang: str, parent=None) -> DocDialog:
    d = DocDialog(doc, lang, parent)
    d.setAttribute(QtCore.Qt.WA_DeleteOnClose)
    d.show()
    return d


class AboutCard(Card):
    """Settings tab: app name, versions, copyright, links and the legal documents."""

    def __init__(self, parent=None):
        super().__init__("info", parent)
        lay = self.setBodyLayout(W.QVBoxLayout())
        lay.setSpacing(6)
        self.name_lbl = W.QLabel(); self.name_lbl.setObjectName("strong")
        self.info_lbl = W.QLabel(); self.info_lbl.setObjectName("note"); self.info_lbl.setWordWrap(True)
        self.link_lbl = W.QLabel(); self.link_lbl.setOpenExternalLinks(True)
        self.link_lbl.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)
        lay.addWidget(self.name_lbl); lay.addWidget(self.info_lbl); lay.addWidget(self.link_lbl)
        row = W.QHBoxLayout(); row.setSpacing(8)
        self.doc_btns = {}
        for doc, ico in (("privacy", "shield"), ("license", "book"), ("notices", "layers")):
            b = W.QPushButton(); IconButton.set(b, ico)
            b.clicked.connect(lambda _=False, doc=doc: self.open_doc(doc))
            row.addWidget(b); self.doc_btns[doc] = b
        row.addStretch(1)
        lay.addLayout(row)
        self.lang = "en"
        self._dialog = None

    def open_doc(self, doc: str):
        self._dialog = show_doc(doc, self.lang, self.window())

    def retranslate(self, lang: str):
        self.lang = lang
        t = lambda k: tr(k, lang)
        self.setTitle(t("about.title"))
        self.name_lbl.setText(f"{t('app.title')} {__version__}")
        m = model_update.current_model()
        model = f"{m['name']} {m['version']}" if m else t("model.missing")
        self.info_lbl.setText(t("about.body").format(model=model, copyright=legal.COPYRIGHT))
        self.link_lbl.setText(f'<a href="{legal.REPO_URL}">{t("about.website")}</a>'
                              f' &nbsp;·&nbsp; <a href="{legal.REPO_URL}/issues">{t("about.issues")}</a>')
        for doc, b in self.doc_btns.items():
            b.setText(t(f"about.{doc}"))
