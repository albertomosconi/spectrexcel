import base64
import hashlib
import os
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import requests
from packaging.version import InvalidVersion, Version


API_URL = "https://api.github.com/repos/albertomosconi/spectrexcel/releases/latest"
REPOSITORY_URL = "https://github.com/albertomosconi/spectrexcel"
CHECKSUM_ASSET = "SHA256SUMS"
ASSET_NAMES = {
    "win32": "spectrexcel-windows-x86_64.exe",
    "linux": "SpectrExcel-x86_64.AppImage",
}
REQUEST_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "SpectrExcel updater",
    "X-GitHub-Api-Version": "2022-11-28",
}


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    download_url: str
    size: int


@dataclass(frozen=True)
class UpdateRelease:
    tag: str
    version: Version
    asset: ReleaseAsset
    checksums: ReleaseAsset
    page_url: str


@dataclass(frozen=True)
class InstallTarget:
    platform: str
    path: Path


@dataclass(frozen=True)
class PreparedUpdate:
    release: UpdateRelease
    downloaded_path: Path
    target: InstallTarget


def find_update(current_version: str, platform: str | None = None) -> UpdateRelease | None:
    platform = platform or sys.platform
    asset_name = ASSET_NAMES.get(platform)
    if asset_name is None:
        raise UpdateError(f"automatic updates are not supported on {platform}")

    response = requests.get(API_URL, headers=REQUEST_HEADERS, timeout=10)
    response.raise_for_status()
    release = response.json()
    tag = release.get("tag_name", "")
    try:
        available_version = Version(tag.removeprefix("v"))
        installed_version = Version(current_version)
    except InvalidVersion as error:
        raise UpdateError(f"invalid release version: {error}") from error

    if available_version <= installed_version:
        return None

    assets = {
        asset.get("name"): asset
        for asset in release.get("assets", [])
        if asset.get("name")
        and asset.get("browser_download_url")
        and isinstance(asset.get("size"), int)
    }
    missing = [name for name in (asset_name, CHECKSUM_ASSET) if name not in assets]
    if missing:
        raise UpdateError(f"release {tag} is missing {', '.join(missing)}")

    return UpdateRelease(
        tag=tag,
        version=available_version,
        asset=ReleaseAsset(
            asset_name,
            assets[asset_name]["browser_download_url"],
            assets[asset_name]["size"],
        ),
        checksums=ReleaseAsset(
            CHECKSUM_ASSET,
            assets[CHECKSUM_ASSET]["browser_download_url"],
            assets[CHECKSUM_ASSET]["size"],
        ),
        page_url=release.get("html_url", REPOSITORY_URL + "/releases/latest"),
    )


def detect_install_target(
    platform: str | None = None,
    executable: str | None = None,
    environ: Mapping[str, str] | None = None,
    frozen: bool | None = None,
) -> InstallTarget:
    platform = platform or sys.platform
    environ = environ if environ is not None else os.environ
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen

    if platform == "win32" and frozen:
        path = Path(executable or sys.executable).resolve()
    elif platform == "linux" and environ.get("APPIMAGE"):
        path = Path(environ["APPIMAGE"]).resolve()
    else:
        raise UpdateError("automatic updates require the installed executable or AppImage")

    if not path.is_file():
        raise UpdateError(f"installed application was not found at {path}")
    if not os.access(path.parent, os.W_OK):
        raise UpdateError(f"the application directory is not writable: {path.parent}")
    return InstallTarget(platform, path)


def prepare_update(
    release: UpdateRelease, target: InstallTarget | None = None
) -> PreparedUpdate:
    target = target or detect_install_target()
    if not 0 < release.asset.size <= 500 * 1024 * 1024:
        raise UpdateError(f"invalid download size for {release.asset.name}")
    if not 0 < release.checksums.size <= 1024 * 1024:
        raise UpdateError("invalid checksum manifest size")
    try:
        manifest = bytearray()
        with requests.get(
            release.checksums.download_url,
            headers=REQUEST_HEADERS,
            timeout=30,
            stream=True,
        ) as checksum_response:
            checksum_response.raise_for_status()
            for chunk in checksum_response.iter_content(chunk_size=64 * 1024):
                manifest.extend(chunk)
                if len(manifest) > release.checksums.size:
                    raise UpdateError("checksum manifest exceeded its declared size")
        if len(manifest) != release.checksums.size:
            raise UpdateError("checksum manifest size does not match the release")
        try:
            manifest_text = manifest.decode("utf-8")
        except UnicodeDecodeError as error:
            raise UpdateError("checksum manifest is not valid UTF-8") from error
        expected_checksum = _checksum_for(manifest_text, release.asset.name)

        download_directory = target.path.parent
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.path.name}-update-", dir=download_directory
        )
        os.close(file_descriptor)
        downloaded_path = Path(temporary_name)
        digest = hashlib.sha256()
        downloaded_size = 0
        try:
            with requests.get(
                release.asset.download_url,
                headers=REQUEST_HEADERS,
                timeout=(10, 120),
                stream=True,
            ) as response:
                response.raise_for_status()
                with downloaded_path.open("wb") as output:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            downloaded_size += len(chunk)
                            if downloaded_size > release.asset.size:
                                raise UpdateError(
                                    f"download exceeded the declared size for {release.asset.name}"
                                )
                            output.write(chunk)
                            digest.update(chunk)
            if downloaded_size != release.asset.size:
                raise UpdateError(f"download size does not match for {release.asset.name}")
            if digest.hexdigest() != expected_checksum:
                raise UpdateError(f"checksum verification failed for {release.asset.name}")
            if target.platform == "linux":
                downloaded_path.chmod(
                    downloaded_path.stat().st_mode
                    | stat.S_IXUSR
                    | stat.S_IXGRP
                    | stat.S_IXOTH
                )
        except Exception:
            downloaded_path.unlink(missing_ok=True)
            raise
    except requests.RequestException as error:
        raise UpdateError(f"unable to download update: {error}") from error

    return PreparedUpdate(release, downloaded_path, target)


def launch_replacement(update: PreparedUpdate, current_pid: int | None = None) -> None:
    current_pid = current_pid or os.getpid()
    if update.target.platform == "win32":
        _launch_windows_replacement(update, current_pid)
    elif update.target.platform == "linux":
        _launch_linux_replacement(update, current_pid)
    else:
        raise UpdateError(f"automatic updates are not supported on {update.target.platform}")


def confirm_update_startup(environ: Mapping[str, str] | None = None) -> None:
    environ = environ if environ is not None else os.environ
    marker_value = environ.get("SPECTREXCEL_UPDATE_MARKER")
    if not marker_value:
        return
    try:
        target = detect_install_target(environ=environ)
        marker = Path(marker_value).resolve()
        expected_prefix = f".{target.path.name}-update-"
        if (
            marker.parent == target.path.parent
            and marker.name.startswith(expected_prefix)
            and marker.name.endswith(".success")
        ):
            marker.write_text("ready", encoding="ascii")
    except (OSError, UpdateError):
        pass


def _checksum_for(manifest: str, asset_name: str) -> str:
    for line in manifest.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) != 2:
            continue
        digest, filename = parts
        if filename.lstrip("*") == asset_name and len(digest) == 64:
            try:
                int(digest, 16)
            except ValueError:
                continue
            return digest.lower()
    raise UpdateError(f"no valid checksum found for {asset_name}")


def _launch_windows_replacement(update: PreparedUpdate, current_pid: int) -> None:
    script = """$Target = $env:SPECTREXCEL_UPDATE_TARGET
$Update = $env:SPECTREXCEL_UPDATE_FILE
$OldPid = [int]$env:SPECTREXCEL_UPDATE_PID
$ErrorActionPreference = "Stop"
$Backup = "$Target.old"
$Marker = "$Update.success"
$Process = $null
for ($Attempt = 0; $Attempt -lt 120; $Attempt++) {
    if (-not (Get-Process -Id $OldPid -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Seconds 1
}
if (Get-Process -Id $OldPid -ErrorAction SilentlyContinue) {
    Remove-Item $Update -Force -ErrorAction SilentlyContinue
    exit 1
}
try {
    Remove-Item $Backup, $Marker -Force -ErrorAction SilentlyContinue
    Move-Item $Target $Backup -Force
    Move-Item $Update $Target -Force
    $env:SPECTREXCEL_UPDATE_MARKER = $Marker
    $Process = Start-Process -FilePath $Target -PassThru
    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
        if (Test-Path $Marker) { $Ready = $true; break }
        if ($Process.HasExited) { break }
        Start-Sleep -Seconds 1
    }
    if (-not $Ready) { throw "The updated application did not start successfully" }
    Remove-Item $Backup, $Marker -Force -ErrorAction SilentlyContinue
} catch {
    if ($Process -and -not $Process.HasExited) { Stop-Process -Id $Process.Id -Force }
    Remove-Item $Marker -Force -ErrorAction SilentlyContinue
    if (Test-Path $Backup) {
        Remove-Item $Target -Force -ErrorAction SilentlyContinue
        Move-Item $Backup $Target -Force
    }
    Remove-Item $Update -Force -ErrorAction SilentlyContinue
    Remove-Item Env:SPECTREXCEL_UPDATE_MARKER -ErrorAction SilentlyContinue
    if (Test-Path $Target) { Start-Process -FilePath $Target }
}
"""
    encoded_script = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    environment = os.environ.copy()
    environment.update(
        {
            "SPECTREXCEL_UPDATE_TARGET": str(update.target.path),
            "SPECTREXCEL_UPDATE_FILE": str(update.downloaded_path),
            "SPECTREXCEL_UPDATE_PID": str(current_pid),
        }
    )
    creation_flags = (
        subprocess.CREATE_NEW_PROCESS_GROUP
        | subprocess.DETACHED_PROCESS
        | subprocess.CREATE_NO_WINDOW
    )
    try:
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                encoded_script,
            ],
            close_fds=True,
            creationflags=creation_flags,
            env=environment,
        )
    except Exception:
        update.downloaded_path.unlink(missing_ok=True)
        raise


def _launch_linux_replacement(update: PreparedUpdate, current_pid: int) -> None:
    script = Path(f"{update.downloaded_path}.sh")
    script.write_text(
        """#!/bin/sh
target=$1
replacement=$2
pid=$3
backup="${target}.old"
marker="${replacement}.success"
attempt=0
while kill -0 "$pid" 2>/dev/null && [ "$attempt" -lt 120 ]; do
    sleep 1
    attempt=$((attempt + 1))
done
if kill -0 "$pid" 2>/dev/null; then
    rm -f "$replacement" "$0"
    exit 1
fi
rm -f "$backup" "$marker"
mv "$target" "$backup" || exit 1
if ! mv "$replacement" "$target"; then
    mv "$backup" "$target"
    exit 1
fi
chmod +x "$target"
SPECTREXCEL_UPDATE_MARKER="$marker" "$target" >/dev/null 2>&1 &
child=$!
ready=false
attempt=0
while [ "$attempt" -lt 30 ]; do
    if [ -f "$marker" ]; then ready=true; break; fi
    if ! kill -0 "$child" 2>/dev/null; then break; fi
    sleep 1
    attempt=$((attempt + 1))
done
if [ "$ready" = true ]; then
    rm -f "$backup" "$marker"
else
    kill "$child" 2>/dev/null || true
    attempt=0
    while kill -0 "$child" 2>/dev/null && [ "$attempt" -lt 5 ]; do
        sleep 1
        attempt=$((attempt + 1))
    done
    kill -KILL "$child" 2>/dev/null || true
    rm -f "$target" "$marker"
    mv "$backup" "$target"
    "$target" >/dev/null 2>&1 &
fi
rm -f "$0"
""",
        encoding="ascii",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    try:
        subprocess.Popen(
            [
                "/bin/sh",
                str(script),
                str(update.target.path),
                str(update.downloaded_path),
                str(current_pid),
            ],
            close_fds=True,
            start_new_session=True,
        )
    except Exception:
        script.unlink(missing_ok=True)
        update.downloaded_path.unlink(missing_ok=True)
        raise
