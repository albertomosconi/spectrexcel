from pathlib import Path

import pytest

from spectrexcel.settings import Settings


@pytest.fixture
def config_dir(monkeypatch, tmp_path):
    monkeypatch.setattr("spectrexcel.settings.user_config_path", lambda *_args: tmp_path)
    return tmp_path


@pytest.mark.parametrize("contents", [b"{", b"[]", b"null", b'"text"', b"\xff"])
def test_settings_invalid_file_uses_defaults_and_can_be_replaced(config_dir, contents):
    (config_dir / "settings.json").write_bytes(contents)

    settings = Settings()

    assert settings.get("main/theme", "System") == "System"
    assert settings.set("main/theme", "Light")
    assert Settings().get("main/theme", "System") == "Light"


@pytest.mark.parametrize("stored,default", [
    ('"true"', False), ("1", False), ("null", "System"),
    ('"800"', 300), ("[]", 300), ('"position"', [100, 100]),
])
def test_settings_wrong_value_type_uses_default(config_dir, stored, default):
    (config_dir / "settings.json").write_text('{"value": ' + stored + '}')

    assert Settings().get("value", default) == default


def test_settings_missing_file_returns_default_without_creating_file(config_dir):
    settings = Settings()

    assert settings.get("missing", 300) == 300
    assert not (config_dir / "settings.json").exists()


@pytest.mark.parametrize("failure_point", ["write", "replace"])
def test_settings_failed_save_preserves_previous_file_and_can_retry(config_dir, monkeypatch, failure_point):
    settings = Settings()
    assert settings.set("main/theme", "Dark")
    previous = settings.path.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("disk unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "write_text" if failure_point == "write" else "replace", fail)
        assert not settings.set("main/theme", "Light")

    assert settings.path.read_bytes() == previous
    assert Settings().get("main/theme", "System") == "Dark"
    assert settings.set("main/theme", "Light")
    assert Settings().get("main/theme", "System") == "Light"


def test_settings_unreadable_path_uses_defaults_and_reports_write_failure(config_dir):
    (config_dir / "settings.json").mkdir()

    settings = Settings()

    assert settings.get("main/theme", "System") == "System"
    assert not settings.set("main/theme", "Light")
