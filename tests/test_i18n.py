"""Translations: complete, placeholders intact, English as fallback."""
import json
import re

import pytest

from hypr_screens import config, i18n
from i18n_keys import all_keys

TABLES = json.loads(i18n.LOCALES.read_text(encoding="utf-8"))
PLACEHOLDER = re.compile(r"\{(\w+)\}")


@pytest.fixture(autouse=True)
def english_afterwards():
    yield
    i18n.set_language("en")


def test_every_language_of_the_picker_has_a_table():
    assert set(i18n.LANGUAGES) == {"en", *TABLES} == set(config.LANGUAGE_CODES)


@pytest.mark.parametrize("language", sorted(TABLES))
def test_every_text_is_translated(language):
    missing = sorted(all_keys() - set(TABLES[language]))
    assert missing == [], f"{language} misses {missing[:10]}"


@pytest.mark.parametrize("language", sorted(TABLES))
def test_translations_keep_their_placeholders(language):
    for key, text in TABLES[language].items():
        assert set(PLACEHOLDER.findall(text)) == set(PLACEHOLDER.findall(key)), (language, key)


@pytest.mark.parametrize("language", sorted(TABLES))
def test_no_translation_is_left_over(language):
    assert sorted(set(TABLES[language]) - all_keys()) == []


def test_english_is_the_default_and_the_fallback():
    assert i18n.set_language("xx") == "en"
    assert i18n.t("Screens") == "Screens"
    i18n.set_language("de")
    assert i18n.t("Screens") == "Bildschirme"
    assert i18n.t("Charge limit {limit} %", limit=80) == "Ladelimit 80 %"
    assert i18n.t("A text nobody translated") == "A text nobody translated"


def test_the_language_is_kept_in_the_config():
    assert config.default_config()["language"] == "en"
    assert config.normalize({"language": "fr"})["language"] == "fr"
    assert config.normalize({"language": "klingon"})["language"] == "en"
