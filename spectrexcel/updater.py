import sys
from dataclasses import dataclass

import requests
from packaging.version import InvalidVersion, Version

from spectrexcel.i18n import _


API_URL = "https://api.github.com/repos/albertomosconi/spectrexcel/releases/latest"
REPOSITORY_URL = "https://github.com/albertomosconi/spectrexcel"
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


@dataclass(frozen=True)
class UpdateRelease:
    tag: str
    version: Version
    asset: ReleaseAsset
    notes: str = ""


def format_notes(body: str) -> str:
    """Convert a GitHub release body into plain text for the update dialog."""
    lines: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith("### "):
            line = f"{line[4:].strip()}:"
        elif line.startswith("## ") or line.startswith("**Full Changelog**"):
            continue
        if not line:
            if lines and lines[-1]:
                lines.append("")
            continue
        lines.append(line)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def find_update(current_version: str, platform: str | None = None) -> UpdateRelease | None:
    platform = platform or sys.platform
    asset_name = ASSET_NAMES.get(platform)
    if asset_name is None:
        raise UpdateError(
            _("updates are not supported on {platform}").format(platform=platform)
        )

    response = requests.get(API_URL, headers=REQUEST_HEADERS, timeout=10)
    response.raise_for_status()
    release = response.json()
    tag = release.get("tag_name", "")
    try:
        available_version = Version(tag.removeprefix("v"))
        installed_version = Version(current_version)
    except InvalidVersion as error:
        raise UpdateError(
            _("invalid release version: {error}").format(error=error)
        ) from error

    if available_version <= installed_version:
        return None

    asset = next(
        (
            asset
            for asset in release.get("assets", [])
            if asset.get("name") == asset_name and asset.get("browser_download_url")
        ),
        None,
    )
    if asset is None:
        raise UpdateError(
            _("release {tag} is missing {asset}").format(tag=tag, asset=asset_name)
        )

    return UpdateRelease(
        tag=tag,
        version=available_version,
        asset=ReleaseAsset(asset_name, asset["browser_download_url"]),
        notes=release.get("body") or "",
    )
