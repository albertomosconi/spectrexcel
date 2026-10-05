"""Source snapshots and optional workbook details in the app's language."""

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Callable

import pandas as pd
from xlsxwriter import Workbook

from spectrexcel.i18n import _

from .parsing import ParseError


@dataclass(frozen=True)
class SourceInfo:
    filename: str
    sha256: str

    @classmethod
    def from_path(cls, path: Path) -> "SourceInfo":
        digest = sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return cls(path.name, digest.hexdigest())


def parse_with_source(path: Path, parser: Callable[..., pd.DataFrame]) -> pd.DataFrame:
    # Snapshot during loading, not export: files may change after parsing.
    try:
        contents = path.read_bytes()
        source = SourceInfo(path.name, sha256(contents).hexdigest())
        dataframe = parser(path, contents=contents)
    except OSError as error:
        raise ParseError(_("Unable to read file contents: {error}").format(error=error)) from error
    dataframe.attrs["source_info"] = source
    return dataframe


def write_info_sheet(
    workbook: Workbook,
    assay: str,
    sources: tuple[SourceInfo, ...],
    settings: dict[str, str | int | float | bool],
    steps: list[str],
) -> None:
    try:
        app_version = version("spectrexcel")
    except PackageNotFoundError:
        app_version = _("unknown")
    sheet = workbook.add_worksheet("info")
    sheet.set_column(0, 0, 32)
    sheet.set_column(1, 1, 65)
    sheet.set_column(2, 2, 66)
    header_format = workbook.add_format({"bold": True})
    headers = (_("Sources"), _("Settings"), _("Processing"))
    rows = [
        [_("SpectrExcel version"), app_version],
        [_("Export timestamp"), datetime.now().astimezone().isoformat(timespec="seconds")],
        [_("Assay"), _(assay)],
        [_("Reproduction"), _("Retain original input files; hashes identify the loaded inputs.")],
        [],
        [headers[0], _("Filename"), "SHA-256"],
        *([_("Source file"), source.filename, source.sha256] for source in sources),
        [],
        [headers[1], _("Value")],
        *([
            _(key),
            (_("Yes") if value else _("No")) if isinstance(value, bool)
            else _(value) if isinstance(value, str) else value,
        ] for key, value in settings.items()),
        [],
        [headers[2], _("Step")],
        *([_("Processing step"), _(step)] for step in steps),
    ]
    for row, values in enumerate(rows):
        cell_format = (
            header_format
            if values and values[0] in headers else None
        )
        for column, value in enumerate(values):
            if isinstance(value, str):
                # Filenames must remain literal even when starting with '='.
                sheet.write_string(row, column, value, cell_format)
            else:
                sheet.write(row, column, value, cell_format)
