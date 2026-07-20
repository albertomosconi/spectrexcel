import string

import pytest

from spectrexcel import i18n
from spectrexcel.i18n import _, detect_language
from spectrexcel.settings import Settings


@pytest.fixture(autouse=True)
def restore_language():
    previous = i18n.get_language()
    yield
    i18n.set_language(previous)


def test_english_is_the_identity():
    i18n.set_language("en")

    assert _("Generate Excel") == "Generate Excel"
    assert _("{count} files ready").format(count=3) == "3 files ready"


def test_italian_translation_lookup():
    i18n.set_language("it")

    assert _("Generate Excel") == "Genera Excel"
    assert _("{count} files ready").format(count=3) == "3 file pronti"


def test_unknown_string_falls_back_to_english():
    i18n.set_language("it")

    assert _("a string nobody translated") == "a string nobody translated"


def test_set_language_rejects_unknown_codes():
    i18n.set_language("fr")

    assert i18n.get_language() == "en"


def test_every_translation_has_content():
    assert i18n.TRANSLATIONS_IT
    for source, translated in i18n.TRANSLATIONS_IT.items():
        assert source.strip()
        assert translated.strip()


def test_format_placeholders_are_preserved():
    def fields(text: str) -> set[str]:
        return {
            name
            for _, name, _, _ in string.Formatter().parse(text)
            if name is not None
        }

    for source, translated in i18n.TRANSLATIONS_IT.items():
        assert fields(source) == fields(translated), source


def test_detect_language_defaults_to_english(monkeypatch):
    monkeypatch.setattr(i18n.locale, "getlocale", lambda: (None, None))
    for name in ("LANGUAGE", "LC_ALL", "LANG"):
        monkeypatch.delenv(name, raising=False)

    assert detect_language() == "en"


def test_detect_language_from_locale(monkeypatch):
    monkeypatch.setattr(i18n.locale, "getlocale", lambda: ("it_IT", "UTF-8"))

    assert detect_language() == "it"


def test_detect_language_from_windows_locale_name(monkeypatch):
    monkeypatch.setattr(i18n.locale, "getlocale", lambda: ("Italian_Italy", "cp1252"))

    assert detect_language() == "it"


def test_detect_language_from_environment(monkeypatch):
    monkeypatch.setattr(i18n.locale, "getlocale", lambda: (None, None))
    monkeypatch.setenv("LANG", "it_IT.UTF-8")

    assert detect_language() == "it"


def test_language_preference_is_persisted(monkeypatch, tmp_path):
    monkeypatch.setattr("spectrexcel.settings.user_config_path", lambda *_args: tmp_path)

    settings = Settings()
    assert settings.get("main/language", detect_language()) in i18n.LANGUAGES
    assert settings.set("main/language", "it")

    assert Settings().get("main/language", "en") == "it"
