"""Translations for the settings window.

Every text is written in English in the code and passed through t(); the
English text is its own key in locales.json. A language without a text, or a
text without a translation, shows the English one.
"""
import json
from pathlib import Path

from hypr_screens import config

LOCALES = Path(__file__).with_name("locales.json")
DEFAULT = "en"
# Shown in their own language in the picker.
LANGUAGES = {
    "en": "English",
    "de": "Deutsch",
    "es": "Español",
    "fr": "Français",
    "it": "Italiano",
}

_language = DEFAULT
_table: dict[str, str] = {}


def load_table(language: str) -> dict[str, str]:
    if language == DEFAULT:
        return {}
    try:
        tables = json.loads(LOCALES.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    table = tables.get(language)
    return {str(k): str(v) for k, v in table.items() if v} if isinstance(table, dict) else {}


def set_language(language: str | None) -> str:
    global _language, _table
    _language = language if language in LANGUAGES else DEFAULT
    _table = load_table(_language)
    return _language


def language() -> str:
    return _language


def use_configured() -> str:
    return set_language(config.load().get("language"))


def t(text: str, **values: object) -> str:
    """The text in the chosen language, with {placeholders} filled in."""
    translated = _table.get(text, text)
    if not values:
        return translated
    try:
        return translated.format(**values)
    except (KeyError, IndexError, ValueError):
        return text.format(**values)
