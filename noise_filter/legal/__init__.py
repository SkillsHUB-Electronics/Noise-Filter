"""License, privacy policy and third-party notices, shipped with the app so they can be read offline.

The copies at the repository root (LICENSE, PRIVACY.md, THIRD_PARTY_NOTICES.md) must stay identical to
these files; tests/test_legal.py checks that."""
from __future__ import annotations

from importlib import resources

REPO_URL = "https://github.com/SkillsHUB-Electronics/Noise-Filter"
COPYRIGHT = "© 2026 SkillsHUB Electronics"
# document key -> file name per language ("en" is the fallback)
DOCS = {
    "privacy": {"en": "PRIVACY.md", "id": "PRIVACY.id.md"},
    "license": {"en": "LICENSE.txt"},
    "notices": {"en": "THIRD_PARTY_NOTICES.md"},
}


def file_name(doc: str, lang: str = "en") -> str:
    names = DOCS[doc]
    return names.get(lang) or names["en"]


def text(doc: str, lang: str = "en") -> str:
    return resources.files(__package__).joinpath(file_name(doc, lang)).read_text("utf-8")


def doc_for_file(name: str) -> tuple[str, str] | None:
    """(doc, lang) for a file name used in a relative link between the documents, e.g. "PRIVACY.id.md"."""
    name = name.split("/")[-1].split("#")[0]
    for doc, names in DOCS.items():
        for lang, n in names.items():
            if n == name or (doc == "license" and name == "LICENSE"):
                return doc, lang
    return None
