import sys
from dataclasses import dataclass
from collections.abc import Iterable

import requests
from packaging.version import InvalidVersion, Version

from spectrexcel.i18n import _


RELEASES_URL = "https://api.github.com/repos/albertomosconi/spectrexcel/releases"
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
class ReleaseNotes:
    tag: str
    body: str


@dataclass(frozen=True)
class UpdateRelease:
    tag: str
    version: Version
    asset: ReleaseAsset
    notes: str = ""
    previous_notes: tuple[ReleaseNotes, ...] = ()

    @property
    def all_notes(self) -> tuple[ReleaseNotes, ...]:
        """This release followed by every intermediate new release."""
        return (ReleaseNotes(self.tag, self.notes), *self.previous_notes)


def format_notes(body: str) -> tuple[str, bool]:
    """Convert a GitHub release body into plain text for the update dialog.

    The "Other Changes" section (maintenance commits) is omitted from the
    dialog; the second return value reports whether anything was hidden, so
    the dialog can link to the full release notes on GitHub.
    """
    lines: list[str] = []
    has_hidden = False
    in_other_changes = False
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith("### "):
            in_other_changes = line == "### Other Changes"
            if in_other_changes:
                continue
            line = f"{line[4:].strip()}:"
        elif line.startswith("## ") or line.startswith("**Full Changelog**"):
            in_other_changes = False
            continue
        if not line:
            if lines and lines[-1]:
                lines.append("")
            continue
        if in_other_changes:
            has_hidden = True
            continue
        lines.append(line)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines), has_hidden


def aggregate_notes(entries: Iterable[tuple[str, str]]) -> tuple[str, bool]:
    """Combine the formatted notes of several releases into one text.

    Each non-empty release becomes a "vX.Y.Z:" section, newest first; the
    hidden flag is true when any release hid its "Other Changes" section.
    """
    sections: list[str] = []
    has_hidden = False
    for tag, body in entries:
        notes, hidden = format_notes(body)
        has_hidden = has_hidden or hidden
        if notes:
            sections.append(f"{tag}:\n{notes}")
    return "\n\n".join(sections), has_hidden


def find_update(current_version: str, platform: str | None = None) -> UpdateRelease | None:
    platform = platform or sys.platform
    asset_name = ASSET_NAMES.get(platform)
    if asset_name is None:
        raise UpdateError(
            _("updates are not supported on {platform}").format(platform=platform)
        )

    try:
        installed_version = Version(current_version)
    except InvalidVersion as error:
        raise UpdateError(
            _("invalid release version: {error}").format(error=error)
        ) from error

    response = requests.get(RELEASES_URL, headers=REQUEST_HEADERS, timeout=10)
    response.raise_for_status()
    stable: list[tuple[Version, dict]] = []
    for release in response.json():
        if release.get("draft") or release.get("prerelease"):
            continue
        tag = release.get("tag_name", "")
        try:
            available_version = Version(tag.removeprefix("v"))
        except InvalidVersion:
            continue
        if available_version > installed_version:
            stable.append((available_version, release))
    stable.sort(key=lambda entry: entry[0], reverse=True)
    if not stable:
        return None
    available_version, release = stable[0]
    tag = release.get("tag_name", "")

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
        previous_notes=tuple(
            ReleaseNotes(
                entry[1].get("tag_name", ""), entry[1].get("body") or ""
            )
            for entry in stable[1:]
        ),
    )
