import re
import struct
from pathlib import Path
from struct import iter_unpack
from typing import Callable

import pandas as pd

from spectrexcel.i18n import _

WAVELENGTH_MIN = 190
WAVELENGTH_MAX = 1100
WAVELENGTH_COUNT = WAVELENGTH_MAX - WAVELENGTH_MIN + 1


class ParseError(Exception):
    pass


def parse_txt_file(filepath: Path) -> pd.DataFrame:
    try:
        with filepath.open("r") as fp:
            contents = fp.read()
    except (OSError, UnicodeError) as error:
        raise ParseError(
            _("Unable to read file contents: {error}").format(error=error)
        ) from error

    contents = re.sub(r"[ \t]+", " ", contents.strip())
    contents = contents.splitlines()
    if len(contents) < 2:
        raise ParseError(_("Unable to read file contents: no spectra found."))

    first_line = contents[0]
    if re.fullmatch(r'"[^"\n]+"(?: "[^"\n]+")+', first_line) is None:
        raise ParseError(_("Unable to read file contents: invalid text table."))
    first_line = re.sub(r"<(\d+) nm>", r"\g<1>", first_line)
    columns = first_line[1:-1].split('" "')
    rows = [line.split() for line in contents[1:]]
    if "WL Result" not in columns or any(not row or len(row) > len(columns) for row in rows):
        raise ParseError(_("Unable to read file contents: invalid text table."))
    try:
        df = pd.DataFrame(
            data=[row + [None] * (len(columns) - len(row)) for row in rows],
            columns=columns,
        )
        return df.drop("WL Result", axis=1).apply(pd.to_numeric)
    except ValueError as error:
        raise ParseError(
            _("Unable to read file contents: invalid text table.")
        ) from error


def parse_sd_file(filepath: Path) -> pd.DataFrame:

    if filepath.suffix.upper() != ".SD":
        raise ParseError(_("Invalid file extension"))

    try:
        contents = filepath.read_bytes()
    except OSError as error:
        raise ParseError(
            _("Unable to read file contents: {error}").format(error=error)
        ) from error

    headers = {
        "S a m p l e N a m e ": (
            b"\x53\x00\x61\x00\x6d\x00\x70\x00\x6c\x00\x65"
            b"\x00\x4e\x00\x61\x00\x6d\x00\x65\x00",
            28,
            b"\x09",
        ),
        "(`DataType": (b"\x28\x60\x44\x61\x74\x61\x54\x79\x70\x65", 33, b"\x02"),
    }
    for _key, (header, spacing, end_char) in headers.items():
        if contents.find(header, 0) != -1:
            break
    else:
        header = None

    position = 0
    out = []
    sample_regions = []
    while header is not None:
        header_idx = contents.find(header, position)
        if header_idx == -1:
            break

        start_idx = header_idx + spacing
        end_idx = contents.find(end_char, start_idx)
        next_name_idx = contents.find(header, start_idx)
        if end_idx == -1 or 0 <= next_name_idx < end_idx:
            raise ParseError(
                _("Unable to read file contents: unterminated sample name.")
            )

        out.append(decode_string_with_fallback(contents[start_idx:end_idx]))
        sample_regions.append((header_idx, end_idx + 1))
        position = end_idx

    df = pd.DataFrame([[s] for s in out], columns=["#Sample"])

    def find_spectrum_header(marker: bytes, position: int) -> int:
        # Sample names may contain literal (AU), including its UTF-16 signature.
        header_idx = contents.find(marker, position)
        while header_idx != -1:
            name_end = next(
                (end for start, end in sample_regions if start <= header_idx < end),
                None,
            )
            if name_end is None:
                return header_idx
            header_idx = contents.find(marker, name_end)
        return -1

    headers = {
        "( A U ) ": (b"\x28\x00\x41\x00\x55\x00\x29\x00", 17),
        "(AU) ": (b"\x28\x41\x55\x29\x00", 5),
    }
    for _key, (header, spacing) in headers.items():
        if find_spectrum_header(header, 0) != -1:
            break
    else:
        raise ParseError(_("Unable to read file contents: no headers found."))

    # Recover a contiguous tail of complete spectra and known name metadata.
    # Legacy exports may put names after their spectrum payloads. This
    # detects an unlabeled next record swallowed by a truncated payload, without
    # interpreting arbitrary (AU) bytes inside absorbances as record headers.
    spectrum_boundaries = set()
    record_end = len(contents)
    record_size = spacing + WAVELENGTH_COUNT * 8
    while record_end:
        name_start = next(
            (start for start, end in sample_regions if end == record_end), None
        )
        if name_start is not None:
            record_end = name_start
            continue
        if record_end < record_size:
            break
        record_start = record_end - record_size
        if not contents.startswith(header, record_start):
            break
        spectrum_boundaries.add(record_start)
        record_end = record_start

    position = 0
    out = []
    while True:
        header_idx = find_spectrum_header(header, position)
        if header_idx == -1:
            break

        start_idx = header_idx + spacing
        end_idx = start_idx + WAVELENGTH_COUNT * 8
        if end_idx > len(contents) or any(
            start_idx <= sample_start < end_idx for sample_start, _end in sample_regions
        ) or any(
            start_idx <= spectrum_start < end_idx for spectrum_start in spectrum_boundaries
        ):
            raise ParseError(_("Unable to read file contents: truncated spectrum."))

        out.append([val for val, in iter_unpack("<d", contents[start_idx:end_idx])])
        position = end_idx

    # Keep legacy label ordering; missing label entries must not discard
    # complete spectra. More labels than spectra still indicates missing data.
    if not out or len(df) > len(out):
        raise ParseError(
            _("Unable to read file contents: sample and spectrum counts differ.")
        )
    df = pd.concat(
        [df, pd.DataFrame(out, columns=range(WAVELENGTH_MIN, WAVELENGTH_MAX + 1))],
        axis=1,
    )

    for i in range(len(df)):
        if pd.isna(df.at[i, "#Sample"]) or df.at[i, "#Sample"] == "":
            df.at[i, "#Sample"] = i + 1

    return df


def parse_kd_file(filepath: Path) -> pd.DataFrame:

    def _extract_data(
        data: bytes, header: dict, parse_func: Callable
    ) -> tuple[list, list[int]]:
        data_list = []
        header_positions = []
        position = 0
        data_header = header["header"]
        spacing = header["spacing"]
        chunk = WAVELENGTH_COUNT * 8

        while True:
            header_idx = data.find(data_header, position)
            if header_idx == -1:
                break

            data_idx = header_idx + spacing
            data_list.append(parse_func(data, data_idx))
            header_positions.append(header_idx)
            position = data_idx + chunk

        return data_list, header_positions

    def _parse_spectratimes(data: bytes, data_start: int) -> float:
        if data_start + 8 > len(data):
            raise ParseError(
                _("Unable to read file contents: truncated acquisition time.")
            )
        return float(struct.unpack_from("<d", data, data_start)[0])

    def _parse_spectra(data, data_start: int) -> pd.Series:
        data_end = data_start + WAVELENGTH_COUNT * 8
        # Marker-shaped bytes may represent finite double absorbances; only
        # recognized time headers or complete metadata pairs delimit records.
        if data_end > len(data) or any(
            data_start <= position < data_end for position in record_positions
        ):
            raise ParseError(_("Unable to read file contents: truncated spectrum."))
        absorbance_data = data[data_start:data_end]
        absorbance_values = [
            value for (value,) in struct.iter_unpack("<d", absorbance_data)
        ]
        return pd.Series(
            absorbance_values, index=range(WAVELENGTH_MIN, WAVELENGTH_MAX + 1)
        )

    if filepath.suffix.upper() != ".KD":
        raise ParseError(_("Invalid file extension"))

    try:
        contents = filepath.read_bytes()
    except OSError as error:
        raise ParseError(
            _("Unable to read file contents: {error}").format(error=error)
        ) from error

    HEADERS = {
        "NEW": (
            b"\x52\x00\x65\x00\x6c\x00\x54\x00\x69\x00\x6d\x00\x65\x00",
            20,
            b"\x28\x00\x41\x00\x55\x00\x29\x00",
            17,
        ),
        "OLD": (
            b"\x52\x65\x6c\x54\x69\x6d\x65",
            21,
            b"\x28\x41\x55\x29",
            5,
        ),
    }

    for H in HEADERS.values():
        if contents.find(H[0], 0) != -1:
            break
    else:
        raise ParseError(_("Unable to read file contents: no headers found."))

    spectra_times, time_positions = _extract_data(
        contents, {"header": H[0], "spacing": H[1]}, _parse_spectratimes
    )
    record_positions = set(time_positions)
    position = contents.find(H[0])
    while position != -1:
        # A truncated compact record can make the fixed-size scanner skip the
        # next acquisition. Recover boundaries with paired time/AU metadata,
        # supporting both compact and spectrum-sized-padding layouts.
        after_time = position + H[1] + 8
        if any(
            contents.startswith(H[2], offset)
            for offset in (after_time, after_time + WAVELENGTH_COUNT * 8)
        ):
            record_positions.add(position)
        position = contents.find(H[0], position + len(H[0]))
    spectra_list, _spectrum_positions = _extract_data(
        contents, {"header": H[2], "spacing": H[3]}, _parse_spectra
    )
    if not spectra_times or not spectra_list:
        raise ParseError(_("Unable to read file contents: no spectra found."))
    if len(spectra_times) != len(spectra_list):
        raise ParseError(
            _("Unable to read file contents: time and spectrum counts differ.")
        )

    df = pd.concat(spectra_list, axis=1)
    df.index = pd.Index(
        range(WAVELENGTH_MIN, WAVELENGTH_MAX + 1), name="Wavelength (nm)"
    )
    df.columns = spectra_times

    return df


def decode_string_with_fallback(byte_string: bytes) -> str:
    byte_string = byte_string.replace(b"\x00", b"")

    for encoding in [
        "utf8",
        "latin1",
        "windows-1252",
        "latin9",
        "cyrillic",
        "windows-1251",
        "latin2",
        "latin5",
        "sjis",
        "korean",
        "gb18030",
        "big5",
        "utf16",
    ]:
        try:
            return byte_string.decode(encoding)
        except UnicodeDecodeError:
            continue
    return byte_string.decode("utf8", "replace")
