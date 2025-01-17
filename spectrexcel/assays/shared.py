import re
from pathlib import Path
from struct import iter_unpack
from typing import Callable, Tuple

import pandas as pd
from PyQt6 import QtWidgets as widgets


class AssayWidget(widgets.QWidget):
    def __init__(self, log: Callable[[str | list[str]], None]):
        super().__init__()

        self.log = log


def parse_txt_file(filepath: Path) -> pd.DataFrame:

    with filepath.open("r") as fp:
        contents = fp.read()

    contents = re.sub(r"[ \t]+", " ", contents.strip())
    contents = contents.split("\n")

    # TODO: validate file format

    first_line = contents[0]
    first_line = re.sub(r"<(\d+) nm>", r"\g<1>", first_line)
    columns = first_line[1:-1].split('" "')

    df = pd.DataFrame(
        data=[line.split(" ") for line in contents[1:]],
        columns=columns,
    )

    df = df.drop("WL Result", axis=1)
    df = df.apply(pd.to_numeric)

    return df


def parse_sd_file(filepath: Path) -> pd.DataFrame:

    if filepath.suffix.upper() != ".SD":
        raise Exception("Invalid file extension")

    with filepath.open("rb") as fp:
        contents = fp.read()

    headers = {
        "S a m p l e N a m e ": (
            b"\x53\x00\x61\x00\x6D\x00\x70\x00\x6C\x00\x65"
            b"\x00\x4E\x00\x61\x00\x6D\x00\x65\x00",
            28,
            b"\x09",
        ),
        "(`DataType": (b"\x28\x60\x44\x61\x74\x61\x54\x79\x70\x65", 33, b"\x02"),
    }
    for _, (header, spacing, end_char) in headers.items():
        if contents.find(header, 0) != -1:
            break

    position = 0
    out = []
    while True:
        header_idx = contents.find(header, position)
        if header_idx == -1:
            break

        start_idx = header_idx + spacing
        end_idx = contents.find(end_char, start_idx)
        end_idx = end_idx if end_idx != -1 else None
        if end_idx is None:
            break

        out.append(decode_string_with_fallback(contents[start_idx:end_idx]))
        position = end_idx

    df = pd.DataFrame([[s] for s in out], columns=["#Sample"])

    headers = {
        "( A U ) ": (b"\x28\x00\x41\x00\x55\x00\x29\x00", 17),
        "(AU) ": (b"\x28\x41\x55\x29\x00", 5),
    }
    for _, (header, spacing) in headers.items():
        if contents.find(header, 0) != -1:
            break

    position = 0
    out = []
    while True:
        header_idx = contents.find(header, position)
        if header_idx == -1:
            break

        start_idx = header_idx + spacing
        end_idx = start_idx + (1100 - 190 + 1) * 8

        out.append([val for val, in iter_unpack("<d", contents[start_idx:end_idx])])
        position = end_idx

    df = pd.concat([df, pd.DataFrame(out, columns=range(190, 1101))], axis=1)

    for i in range(len(df)):
        if df.at[i, "#Sample"] == "":
            df.at[i, "#Sample"] = i + 1

    return df


def clean_duplicate_spectra(df: pd.DataFrame) -> Tuple[pd.DataFrame, bool]:

    halfway_row = int(len(df) / 2)
    df_data = df.drop("#Sample", axis=1)
    df_1st_half = df_data.head(halfway_row).reset_index(drop=True)
    df_2nd_half = df_data.tail(halfway_row).reset_index(drop=True)

    if df_1st_half.equals(df_2nd_half):
        df = df.head(halfway_row)
        return df, True

    return df, False


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
