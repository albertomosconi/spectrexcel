import pytest
from packaging.version import Version

from spectrexcel import main, updater


WINDOWS_ASSET = "spectrexcel-windows-x86_64.exe"
LINUX_ASSET = "SpectrExcel-x86_64.AppImage"


class FakeResponse:
    def __init__(self, json_data):
        self._json_data = json_data

    def json(self):
        return self._json_data

    def raise_for_status(self):
        return None


def release_payload(tag="v1.1.0"):
    return {
        "tag_name": tag,
        "assets": [
            {
                "name": WINDOWS_ASSET,
                "browser_download_url": "https://example/windows",
            },
            {
                "name": LINUX_ASSET,
                "browser_download_url": "https://example/linux",
            },
        ],
    }


def test_find_update_selects_platform_download(monkeypatch):
    monkeypatch.setattr(
        updater.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(release_payload()),
    )

    update = updater.find_update("1.0.3", platform="linux")

    assert update is not None
    assert update.tag == "v1.1.0"
    assert update.version == Version("1.1.0")
    assert update.asset == updater.ReleaseAsset(LINUX_ASSET, "https://example/linux")


def test_find_update_returns_none_for_installed_version(monkeypatch):
    monkeypatch.setattr(
        updater.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(release_payload()),
    )

    assert updater.find_update("1.1.0", platform="win32") is None


def test_find_update_rejects_missing_platform_asset(monkeypatch):
    payload = release_payload()
    payload["assets"] = payload["assets"][:1]
    monkeypatch.setattr(
        updater.requests, "get", lambda *args, **kwargs: FakeResponse(payload)
    )

    with pytest.raises(updater.UpdateError, match=LINUX_ASSET):
        updater.find_update("1.0.3", platform="linux")


def test_find_update_rejects_unsupported_platform():
    with pytest.raises(updater.UpdateError, match="not supported"):
        updater.find_update("1.0.3", platform="darwin")


def test_download_closes_only_after_browser_opens(monkeypatch):
    app = object.__new__(main.SpectrExcelApp)
    app.has_running_tasks = lambda: False
    app.log = lambda _message: None
    browser_results = iter((False, True))
    stopped = []
    monkeypatch.setattr(main.webbrowser, "open", lambda _url: next(browser_results))
    monkeypatch.setattr(main.dpg, "stop_dearpygui", lambda: stopped.append(True))
    release = updater.UpdateRelease(
        "v1.1.0",
        Version("1.1.0"),
        updater.ReleaseAsset(WINDOWS_ASSET, "https://example/windows"),
    )

    app._open_update_download(release)
    assert stopped == []

    app._open_update_download(release)
    assert stopped == [True]
