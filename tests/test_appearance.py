import subprocess

from spectrexcel.appearance import resolve_theme, system_theme
from spectrexcel.settings import Settings


def test_explicit_theme_is_unchanged():
    assert resolve_theme("Light") == "Light"
    assert resolve_theme("Dark") == "Dark"


def test_invalid_theme_uses_system_fallback():
    assert resolve_theme("invalid", platform="unsupported") == "Dark"


def test_linux_system_theme_uses_gsettings(monkeypatch):
    def run(*_args, **_kwargs):
        return subprocess.CompletedProcess([], 0, stdout="'prefer-dark'\n")

    monkeypatch.setattr(subprocess, "run", run)

    assert system_theme("linux") == "Dark"


def test_system_theme_falls_back_to_dark(monkeypatch):
    def run(*_args, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", run)

    assert system_theme("linux") == "Dark"


def test_theme_preference_is_persisted(monkeypatch, tmp_path):
    monkeypatch.setattr("spectrexcel.settings.user_config_path", lambda *_args: tmp_path)

    settings = Settings()
    assert settings.set("main/theme", "Light")

    assert Settings().get("main/theme", "System") == "Light"
