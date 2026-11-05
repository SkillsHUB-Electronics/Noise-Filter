import json
from importlib import resources

_cache: dict[str, dict] = {}


def load(lang: str) -> dict:
    if lang not in _cache:
        _cache[lang] = json.loads(resources.files(__package__).joinpath(f"{lang}.json").read_text("utf-8"))
    return _cache[lang]


def tr(key: str, lang: str = "en") -> str:
    """English is the primary language and the fallback."""
    return load(lang).get(key) or load("en").get(key, key)
