import base64
import hashlib
import os
from pathlib import Path

import pytest
from packaging.version import Version

from spectrexcel import updater


WINDOWS_ASSET = "spectrexcel-windows-x86_64.exe"
LINUX_ASSET = "SpectrExcel-x86_64.AppImage"


class FakeResponse:
    def __init__(self, *, json_data=None, text="", content=None):
        self._json_data = json_data
        self.text = text
        self.content = text.encode() if content is None else content

    def json(self):
        return self._json_data

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        del chunk_size
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False


def release_payload(tag="v1.1.0", include_checksums=True):
    assets = [
        {
            "name": WINDOWS_ASSET,
            "browser_download_url": "https://example/windows",
            "size": 100,
        },
        {
            "name": LINUX_ASSET,
            "browser_download_url": "https://example/linux",
            "size": 100,
        },
    ]
    if include_checksums:
        assets.append(
            {
                "name": updater.CHECKSUM_ASSET,
                "browser_download_url": "https://example/checksums",
                "size": 100,
            }
        )
    return {
        "tag_name": tag,
        "html_url": "https://example/release",
        "assets": assets,
    }


def test_find_update_selects_platform_asset(monkeypatch):
    monkeypatch.setattr(
        updater.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(json_data=release_payload()),
    )

    update = updater.find_update("1.0.3", platform="linux")

    assert update is not None
    assert update.tag == "v1.1.0"
    assert update.version == Version("1.1.0")
    assert update.asset.name == LINUX_ASSET
    assert update.checksums.name == updater.CHECKSUM_ASSET


def test_find_update_returns_none_for_installed_version(monkeypatch):
    monkeypatch.setattr(
        updater.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(json_data=release_payload()),
    )

    assert updater.find_update("1.1.0", platform="win32") is None


def test_find_update_rejects_incomplete_release(monkeypatch):
    monkeypatch.setattr(
        updater.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(
            json_data=release_payload(include_checksums=False)
        ),
    )

    with pytest.raises(updater.UpdateError, match="missing SHA256SUMS"):
        updater.find_update("1.0.3", platform="win32")


def test_find_update_rejects_unsupported_platform():
    with pytest.raises(updater.UpdateError, match="not supported"):
        updater.find_update("1.0.3", platform="darwin")


def test_prepare_update_verifies_checksum(monkeypatch, tmp_path):
    target_path = tmp_path / "SpectrExcel.AppImage"
    target_path.write_bytes(b"old")
    content = b"new application"
    checksum = hashlib.sha256(content).hexdigest()
    manifest = f"{checksum}  {LINUX_ASSET}\n"
    responses = iter(
        [
            FakeResponse(text=manifest),
            FakeResponse(content=content),
        ]
    )
    monkeypatch.setattr(
        updater.requests, "get", lambda *args, **kwargs: next(responses)
    )
    release = updater.UpdateRelease(
        tag="v1.1.0",
        version=Version("1.1.0"),
        asset=updater.ReleaseAsset(LINUX_ASSET, "https://example/linux", len(content)),
        checksums=updater.ReleaseAsset(
            "SHA256SUMS", "https://example/checksums", len(manifest.encode())
        ),
        page_url="https://example/release",
    )

    prepared = updater.prepare_update(
        release, updater.InstallTarget("linux", target_path)
    )

    assert prepared.downloaded_path.read_bytes() == content
    if os.name != "nt":
        assert prepared.downloaded_path.stat().st_mode & 0o111
    prepared.downloaded_path.unlink()


def test_prepare_update_removes_invalid_download(monkeypatch, tmp_path):
    target_path = tmp_path / "spectrexcel.exe"
    target_path.write_bytes(b"old")
    responses = iter(
        [
            FakeResponse(text=f"{'0' * 64}  {WINDOWS_ASSET}\n"),
            FakeResponse(content=b"tampered"),
        ]
    )
    monkeypatch.setattr(
        updater.requests, "get", lambda *args, **kwargs: next(responses)
    )
    release = updater.UpdateRelease(
        tag="v1.1.0",
        version=Version("1.1.0"),
        asset=updater.ReleaseAsset(WINDOWS_ASSET, "https://example/windows", 8),
        checksums=updater.ReleaseAsset(
            "SHA256SUMS",
            "https://example/checksums",
            len(f"{'0' * 64}  {WINDOWS_ASSET}\n".encode()),
        ),
        page_url="https://example/release",
    )

    with pytest.raises(updater.UpdateError, match="checksum verification failed"):
        updater.prepare_update(release, updater.InstallTarget("win32", target_path))

    assert list(tmp_path.iterdir()) == [target_path]


def test_detects_linux_appimage(tmp_path):
    appimage = tmp_path / "SpectrExcel.AppImage"
    appimage.write_bytes(b"app")

    target = updater.detect_install_target(
        platform="linux", environ={"APPIMAGE": str(appimage)}
    )

    assert target == updater.InstallTarget("linux", appimage.resolve())


def test_rejects_development_install():
    with pytest.raises(updater.UpdateError, match="installed executable or AppImage"):
        updater.detect_install_target(
            platform="win32", executable=str(Path("python.exe")), frozen=False
        )


def test_confirms_successful_appimage_startup(monkeypatch, tmp_path):
    appimage = tmp_path / "SpectrExcel.AppImage"
    appimage.write_bytes(b"app")
    marker = tmp_path / ".SpectrExcel.AppImage-update-abc.success"
    monkeypatch.setattr(updater.sys, "platform", "linux")

    updater.confirm_update_startup(
        {
            "APPIMAGE": str(appimage),
            "SPECTREXCEL_UPDATE_MARKER": str(marker),
        }
    )

    assert marker.read_text() == "ready"


def test_linux_replacement_waits_for_startup_marker(monkeypatch, tmp_path):
    target_path = tmp_path / "SpectrExcel.AppImage"
    downloaded_path = tmp_path / ".SpectrExcel.AppImage-update-abc"
    target_path.write_bytes(b"old")
    downloaded_path.write_bytes(b"new")
    release = updater.UpdateRelease(
        tag="v1.1.0",
        version=Version("1.1.0"),
        asset=updater.ReleaseAsset(LINUX_ASSET, "https://example/linux", 3),
        checksums=updater.ReleaseAsset("SHA256SUMS", "https://example/checksums", 1),
        page_url="https://example/release",
    )
    launched = []
    monkeypatch.setattr(
        updater.subprocess, "Popen", lambda command, **kwargs: launched.append(command)
    )

    updater.launch_replacement(
        updater.PreparedUpdate(
            release,
            downloaded_path,
            updater.InstallTarget("linux", target_path),
        ),
        current_pid=123,
    )

    script = Path(launched[0][1])
    script_text = script.read_text()
    assert "SPECTREXCEL_UPDATE_MARKER" in script_text
    assert 'mv "$backup" "$target"' in script_text
    script.unlink()
    downloaded_path.unlink()


def test_windows_replacement_uses_stock_powershell(monkeypatch, tmp_path):
    target_path = tmp_path / "spectrexcel.exe"
    downloaded_path = tmp_path / ".spectrexcel.exe-update-abc"
    target_path.write_bytes(b"old")
    downloaded_path.write_bytes(b"new")
    release = updater.UpdateRelease(
        tag="v1.1.0",
        version=Version("1.1.0"),
        asset=updater.ReleaseAsset(WINDOWS_ASSET, "https://example/windows", 3),
        checksums=updater.ReleaseAsset("SHA256SUMS", "https://example/checksums", 1),
        page_url="https://example/release",
    )
    launched = []
    monkeypatch.setattr(updater.subprocess, "CREATE_NEW_PROCESS_GROUP", 1, raising=False)
    monkeypatch.setattr(updater.subprocess, "DETACHED_PROCESS", 2, raising=False)
    monkeypatch.setattr(updater.subprocess, "CREATE_NO_WINDOW", 4, raising=False)
    monkeypatch.setattr(
        updater.subprocess,
        "Popen",
        lambda command, **kwargs: launched.append((command, kwargs)),
    )

    updater.launch_replacement(
        updater.PreparedUpdate(
            release,
            downloaded_path,
            updater.InstallTarget("win32", target_path),
        ),
        current_pid=123,
    )

    command, options = launched[0]
    script = base64.b64decode(command[-1]).decode("utf-16-le")
    assert command[-2] == "-EncodedCommand"
    assert "Wait-Process" not in script
    assert "Move-Item $Target $Backup" in script
    assert "PYINSTALLER_RESET_ENVIRONMENT" in script
    assert options["env"]["SPECTREXCEL_UPDATE_TARGET"] == str(target_path)
    assert options["env"]["SPECTREXCEL_UPDATE_FILE"] == str(downloaded_path)
    assert "SPECTREXCEL_UPDATE_PID" not in options["env"]
    assert not Path(f"{downloaded_path}.ps1").exists()
