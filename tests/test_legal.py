import json
import os
from pathlib import Path

import pytest

from noise_filter import __version__, legal

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("root_name, doc", [("LICENSE", "license"), ("PRIVACY.md", "privacy"),
                                            ("THIRD_PARTY_NOTICES.md", "notices")])
def test_root_copies_match_bundled(root_name, doc):
    assert (ROOT / root_name).read_text("utf-8") == legal.text(doc, "en")


def test_documents_load_in_both_languages():
    for doc in legal.DOCS:
        for lang in ("en", "id"):
            assert len(legal.text(doc, lang)) > 200
    assert "Kebijakan Privasi" in legal.text("privacy", "id")
    assert "MIT License" in legal.text("license")


def test_links_between_documents():
    assert legal.doc_for_file("noise_filter/legal/PRIVACY.id.md") == ("privacy", "id")
    assert legal.doc_for_file("PRIVACY.md") == ("privacy", "en")
    assert legal.doc_for_file("LICENSE") == ("license", "en")
    assert legal.doc_for_file("other.md") is None


def test_privacy_policy_lists_every_uploaded_field():
    """If the app starts sending a new field, the privacy policy must be updated too."""
    text = legal.text("privacy", "en")
    for words in ("audio clip", "noise type", "app version", "operating system", "installation ID",
                  "consent version", "microphone or a file"):
        assert words in text
    assert __version__ in text.splitlines()[2]       # "Last updated: ... (app version X)"


def test_about_card_and_privacy_dialog(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from PySide6 import QtCore, QtWidgets as W
    app = W.QApplication.instance() or W.QApplication([])
    from noise_filter.ui.about import AboutCard, DocDialog
    card = AboutCard()
    card.retranslate("id")
    assert card.title() == "Tentang" and __version__ in card.name_lbl.text()
    assert "MIT" in card.info_lbl.text()
    d = DocDialog("privacy", "en")
    assert "Privacy Policy" in d.view.toPlainText()
    d._link(QtCore.QUrl("noise_filter/legal/PRIVACY.id.md"))      # link to the Indonesian version
    assert "Kebijakan Privasi" in d.view.toPlainText()
    d.show_doc("license", "en")
    assert "MIT License" in d.view.toPlainText()
