import re
import struct
from pathlib import Path
from struct import iter_unpack
from typing import Any, Callable, Tuple

import dearpygui.dearpygui as dpg
import pandas as pd

from spectrexcel.dpi import DisplayScale
from spectrexcel import native_dialogs
from spectrexcel.i18n import _
from spectrexcel.settings import Settings


class AssayView:
    def __init__(
        self,
        log: Callable[[str | list[str]], None],
        submit: Callable[..., None],
        settings: Settings,
        display_scale: DisplayScale,
    ):
        self.log = log
        self._submit = submit
        self.settings = settings
        self.display_scale = display_scale
        self.active = True

    def dispose(self) -> None:
        self.active = False

    def submit(
        self,
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        def if_active(callback: Callable[[Any], None]) -> Callable[[Any], None]:
            return lambda value: callback(value) if self.active else None

        self._submit(task, if_active(on_success), if_active(on_error))

    def open_file_dialog(
        self,
        *,
        title: str,
        callback: Callable[[list[Path]], None],
        filters: dict[str, list[str]],
        default_path: str,
        multiple: bool = False,
    ) -> None:
        try:
            selected = native_dialogs.open_files(title, default_path, filters, multiple)
        except Exception as error:
            self.log(
                _("ERROR: unable to open the system file picker: {error}").format(
                    error=error
                )
            )
            return
        paths = [Path(value) for value in selected if value]
        if paths:
            callback(paths)

    def save_file_dialog(
        self,
        *,
        title: str,
        callback: Callable[[Path], None],
        default_path: str,
        default_filename: str,
    ) -> None:
        try:
            selected = native_dialogs.save_file(
                title,
                default_path,
                default_filename,
                {_("Excel workbook"): ["*.xlsx"]},
            )
        except Exception as error:
            self.log(
                _("ERROR: unable to open the system file picker: {error}").format(
                    error=error
                )
            )
            return
        if not selected:
            return
        selected_path = Path(selected)
        path = (
            selected_path
            if selected_path.suffix.lower() == ".xlsx"
            else selected_path.with_suffix(".xlsx")
        )
        if path != selected_path and path.exists():
            self._confirm_overwrite(path, callback)
        else:
            callback(path)

    def _confirm_overwrite(
        self, path: Path, callback: Callable[[Path], None]
    ) -> None:
        px = self.display_scale.pixels
        tag = "save.overwrite"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)
        with dpg.window(
            label=_("Replace existing file?"),
            tag=tag,
            modal=True,
            no_close=True,
            width=px(430),
            height=px(145),
            pos=self.display_scale.position((185, 175)),
        ):
            dpg.add_text(
                _("{name} already exists. Replace it?").format(name=path.name),
                wrap=px(390),
            )
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label=_("Replace"),
                    width=px(100),
                    callback=lambda: (dpg.delete_item(tag), callback(path)),
                )
                dpg.add_button(
                    label=_("Cancel"),
                    width=px(100),
                    callback=lambda: dpg.delete_item(tag),
                )


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
        raise Exception(_("Invalid file extension"))

    with filepath.open("rb") as fp:
        contents = fp.read()

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
        raise Exception(_("Unable to read file contents: no headers found."))

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
    for _key, (header, spacing) in headers.items():
        if contents.find(header, 0) != -1:
            break
    else:
        raise Exception(_("Unable to read file contents: no headers found."))

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


def parse_kd_file(filepath: Path) -> pd.DataFrame | None:

    def _extract_data(data: bytes, header: dict, parse_func: Callable) -> list | None:
        data_list = []
        position = 0
        data_header = header["header"]
        spacing = header["spacing"]
        chunk = (1100 - 190 + 1) * 8

        while True:
            header_idx = data.find(data_header, position)
            if header_idx == -1:
                break

            data_idx = header_idx + spacing
            data_list.append(parse_func(data, data_idx))
            position = data_idx + chunk

        return data_list if data_list else None

    def _parse_spectratimes(data: bytes, data_start: int) -> float:
        return float(struct.unpack_from("<d", data, data_start)[0])

    def _parse_spectra(data, data_start: int) -> pd.Series:
        data_end = data_start + (1100 - 190 + 1) * 8
        absorbance_data = data[data_start:data_end]
        absorbance_values = [
            value for (value,) in struct.iter_unpack("<d", absorbance_data)
        ]
        return pd.Series(absorbance_values, index=range(190, 1101))

    if filepath.suffix.upper() != ".KD":
        raise Exception(_("Invalid file extension"))

    with filepath.open("rb") as fp:
        contents = fp.read()

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
        raise Exception(_("Unable to read file contents: no headers found."))

    spectra_times = _extract_data(
        contents, {"header": H[0], "spacing": H[1]}, _parse_spectratimes
    )
    if not spectra_times:
        return None

    spectra_list = _extract_data(
        contents, {"header": H[2], "spacing": H[3]}, _parse_spectra
    )
    if not spectra_list:
        return None

    df = pd.concat(spectra_list, axis=1)
    df.index = pd.Index(range(190, 1101), name="Wavelength (nm)")
    df.columns = spectra_times

    return df


def clean_duplicate_spectra(df: pd.DataFrame) -> Tuple[pd.DataFrame, bool]:

    if len(df) < 2 or len(df) % 2 != 0:
        return df, False

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
