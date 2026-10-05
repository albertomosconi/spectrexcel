from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from hashlib import sha256
import struct
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import dearpygui.dearpygui as dpg
import pandas as pd
import pytest

from spectrexcel.assays.cinetiche import Cinetiche, export_kinetics
from spectrexcel.assays.famiglia_di_spettri import FamigliaDiSpettri, export_spectrum_family
from spectrexcel.assays.titolazione import BindingTitolazione, export_binding
from spectrexcel.dpi import DisplayScale
from spectrexcel.assays.parsing import ParseError


NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
ASSAYS = [("binding", BindingTitolazione), ("spectra", FamigliaDiSpettri), ("kinetics", Cinetiche)]


def read_workbook(path):
    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        names = [sheet.get("name") for sheet in workbook.findall("s:sheets/s:sheet", NS)]
        strings = (
            ["".join(item.itertext()) for item in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
            if "xl/sharedStrings.xml" in archive.namelist() else []
        )
        rows = []
        if "info" in names:
            sheet = ET.fromstring(archive.read(f"xl/worksheets/sheet{names.index('info') + 1}.xml"))
            for row in sheet.findall("s:sheetData/s:row", NS):
                values = []
                for cell in row.findall("s:c", NS):
                    value = cell.findtext("s:v", namespaces=NS)
                    values.append(strings[int(value)] if cell.get("t") == "s" else value)
                rows.append(values)
        return names, rows, archive.read("xl/worksheets/sheet1.xml"), archive.read("xl/charts/chart1.xml")


def export(assay, output, **kwargs):
    spectra = pd.DataFrame({0.0: [1.0, 0.25], 10.0: [0.5, 0.1]}, index=[300, 800])
    if assay == "binding":
        frame = pd.DataFrame({"#Sample": ["first"], "Std.Dev.": [0.1], 300: [1.0], 800: [0.25]})
        export_binding(frame, output, 200, 900, -1.0, 2.0, correction_wavelength=800, **kwargs)
    elif assay == "spectra":
        export_spectrum_family(spectra, Path("input.KD"), output, correction_wavelength=800, **kwargs)
    else:
        export_kinetics([("input", spectra)], output, 300, 800, **kwargs)


@pytest.mark.parametrize("assay,cls", ASSAYS)
def test_info_is_opt_in_and_preserves_data_and_chart(tmp_path, assay, cls):
    from spectrexcel.assays.export_info import SourceInfo

    source = SourceInfo("=input.KD", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
    plain, detailed = tmp_path / "plain.xlsx", tmp_path / "detailed.xlsx"
    export(assay, plain)
    export(assay, detailed, info_sources=(source,))

    plain_names, plain_rows, plain_data, plain_chart = read_workbook(plain)
    names, rows, data, chart = read_workbook(detailed)
    assert plain_names == ["data", "raw"] and not plain_rows
    assert names == ["data", "raw", "info"]
    assert data == plain_data and chart == plain_chart
    entries = {row[0]: row[1] for row in rows if len(row) == 2}
    assert entries["SpectrExcel version"] == version("spectrexcel")
    assert datetime.fromisoformat(entries["Export timestamp"]).utcoffset() is not None
    assert entries["Correction wavelength (nm)"] == "800"
    assert ["Source file", source.filename, source.sha256] in rows
    with ZipFile(detailed) as archive:
        info = ET.fromstring(archive.read("xl/worksheets/sheet3.xml"))
        assert not info.findall(".//s:f", NS)
        assert info.find("s:hyperlinks", NS) is None
    assert any("subtract" in " ".join(row).lower() for row in rows)
    assert entries["Assay"] == {"binding": "binding / titration", "spectra": "spectrum family", "kinetics": "kinetics"}[assay]
    if assay == "binding":
        assert entries["X-axis minimum (nm)"] == "200"
        assert entries["Y-axis minimum (AU)"] == "-1"
    elif assay == "spectra":
        assert entries["Chart spectrum stride"] == "2"
    else:
        assert entries["Reading wavelength (nm)"] == "300"


@pytest.mark.parametrize("assay,cls", ASSAYS)
def test_checkbox_defaults_off_below_export_buttons(assay, cls):
    dpg.create_context()
    try:
        dpg.add_theme(tag="theme.accent")
        dpg.add_theme(tag="theme.muted")
        parent = dpg.add_window()
        view = cls(lambda message: None, lambda *args: None, {}, DisplayScale())
        view.build(parent)
        assert dpg.does_item_exist(f"{assay}.info")
        assert dpg.get_value(f"{assay}.info") is False
        children = dpg.get_item_children(parent, 1)
        assert children.index(dpg.get_alias_id(f"{assay}.info")) > children.index(dpg.get_item_parent(f"{assay}.export"))
        assert dpg.get_item_parent(f"{assay}.preview") == dpg.get_item_parent(f"{assay}.export")
    finally:
        dpg.destroy_context()


@pytest.mark.parametrize("assay,cls", ASSAYS)
def test_info_checkbox_remembers_latest_choice_across_assays_and_restarts(monkeypatch, tmp_path, assay, cls):
    from spectrexcel.settings import Settings

    monkeypatch.setattr("spectrexcel.settings.user_config_path", lambda *args: tmp_path)
    dpg.create_context()
    try:
        dpg.add_theme(tag="theme.accent")
        dpg.add_theme(tag="theme.muted")
        current_assay, current_cls = assay, cls
        expected = False
        for enabled in (True, False, True):
            parent = dpg.add_window()
            view = current_cls(lambda message: None, lambda *args: None, Settings(), DisplayScale())
            view.build(parent)
            tag = f"{current_assay}.info"
            assert dpg.get_value(tag) is expected
            callback = dpg.get_item_callback(tag)
            assert callable(callback)
            dpg.set_value(tag, enabled)
            callback(tag, enabled)
            view.dispose()
            dpg.delete_item(parent)
            expected = enabled
            current_assay, current_cls = ASSAYS[(ASSAYS.index((current_assay, current_cls)) + 1) % len(ASSAYS)]
        parent = dpg.add_window()
        view = current_cls(lambda message: None, lambda *args: None, Settings(), DisplayScale())
        view.build(parent)
        assert dpg.get_value(f"{current_assay}.info") is True
    finally:
        dpg.destroy_context()


@pytest.mark.parametrize("assay,cls", ASSAYS)
def test_info_tables_have_bold_headers_and_blank_row_separators(tmp_path, assay, cls):
    from spectrexcel.assays.export_info import SourceInfo

    output = tmp_path / "formatted.xlsx"
    export(assay, output, info_sources=(SourceInfo("input.KD", "abc"),))
    with ZipFile(output) as archive:
        strings = ["".join(item.itertext()) for item in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet3.xml"))
        styles = ET.fromstring(archive.read("xl/styles.xml"))
    fonts = styles.find("s:fonts", NS)
    cell_formats = styles.find("s:cellXfs", NS)
    populated_rows = {int(row.get("r")) for row in sheet.findall("s:sheetData/s:row", NS)
                      if row.findall("s:c", NS)}
    found_headers = []
    for row in sheet.findall("s:sheetData/s:row", NS):
        cells = row.findall("s:c", NS)
        if not cells or cells[0].get("t") != "s":
            continue
        label = strings[int(cells[0].findtext("s:v", namespaces=NS))]
        if label not in ("Sources", "Settings", "Processing"):
            continue
        found_headers.append(label)
        number = int(row.get("r"))
        assert number - 1 not in populated_rows
        assert number - 2 in populated_rows
        for cell in cells:
            font = fonts[int(cell_formats[int(cell.get("s", "0"))].get("fontId"))]
            assert font.find("s:b", NS) is not None
    assert found_headers == ["Sources", "Settings", "Processing"]


def test_source_hash_uses_exact_file_bytes(tmp_path):
    from spectrexcel.assays.export_info import SourceInfo

    source = tmp_path / "=input.KD"
    source.write_bytes(b"abc")
    snapshot = SourceInfo.from_path(source)
    assert snapshot.filename == "=input.KD"
    assert snapshot.sha256 == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_hash_and_parser_share_snapshot_when_file_changes_during_loading(tmp_path):
    from spectrexcel.assays.export_info import parse_with_source

    source = tmp_path / "input.KD"
    source.write_bytes(b"abc")

    def parse(path, *, contents):
        path.write_bytes(b"changed")
        return pd.DataFrame({"bytes": [contents]})

    frame = parse_with_source(source, parse)
    assert frame.iloc[0, 0] == b"abc"
    assert frame.attrs["source_info"].sha256 == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


@pytest.mark.parametrize("extension,parser_name,contents", [
    ("txt", "parse_txt_file", b'"WL Result" "#Sample" "<300 nm>"\n0 1 0.5\n'),
    ("KD", "parse_kd_file", b"invalid"),
    ("SD", "parse_sd_file", b"invalid"),
])
def test_parser_accepts_snapshot_without_rereading_path(tmp_path, extension, parser_name, contents):
    from spectrexcel.assays import parsing

    parser = getattr(parsing, parser_name)
    missing = tmp_path / f"missing.{extension}"
    if extension == "txt":
        frame = parser(missing, contents=contents)
        assert frame.iloc[0].tolist() == [1, 0.5]
    else:
        with pytest.raises(ParseError, match="headers"):
            parser(missing, contents=contents)


def test_missing_source_raises_parse_error(tmp_path):
    from spectrexcel.assays.export_info import parse_with_source

    with pytest.raises(ParseError):
        parse_with_source(tmp_path / "missing.KD", lambda path: pd.DataFrame())


@pytest.mark.parametrize("assay,cls", ASSAYS)
def test_loaded_sources_and_checkbox_reach_export_without_affecting_preview(tmp_path, assay, cls, monkeypatch):
    # Real input parsing and Dear PyGui widgets, without a desktop render loop.
    kd = (b"R\x00e\x00l\x00T\x00i\x00m\x00e\x00" + b"\x00" * 6
          + struct.pack("<d", 2.5) + b"\x00" * (911 * 8)
          + b"(\x00A\x00U\x00)\x00" + b"\x00" * 9
          + struct.pack("<911d", *[i / 1000.0 for i in range(911)]))
    txt = b'"WL Result" "#Sample" "<300 nm>" "<800 nm>"\n0 1 1.0 0.25\n0 2 1.0 0.25\n'
    contents = txt if assay == "binding" else kd
    source = tmp_path / ("input.txt" if assay == "binding" else "input.KD")
    source.write_bytes(contents)
    source_paths = [source]
    source_contents = [contents]
    if assay == "kinetics":
        source = source.rename(tmp_path / "input-10.KD")
        second = tmp_path / "input-2.KD"
        second_contents = kd[:20] + struct.pack("<d", 3.5) + kd[28:]
        second.write_bytes(second_contents)
        source_paths = [source, second]
        source_contents = [contents, second_contents]

    class Settings(dict):
        def set(self, key, value):
            self[key] = value

    def submit(task, on_success, on_error):
        on_success(task())

    dpg.create_context()
    try:
        dpg.create_viewport()
        dpg.add_theme(tag="theme.accent")
        dpg.add_theme(tag="theme.muted")
        parent = dpg.add_window()
        view = cls(lambda message: None, submit, Settings(), DisplayScale())
        view.build(parent)
        if assay == "kinetics":
            view._load_inputs(source_paths)
            assert [name for name, frame in view.datasets] == ["input-2", "input-10"]
            view._show_reorder()
            view._move_dataset(None, None, (0, 1))
            assert [name for name, frame in view.datasets] == ["input-10", "input-2"]
        else:
            view._load_input(source)
        # Hash must describe the loaded data, not whatever is now on disk.
        for path in source_paths:
            path.write_bytes(b"changed after loading")
        previews = []
        monkeypatch.setattr(view, "show_chart_preview", previews.append)
        for enabled in (False, True):
            dpg.set_value(f"{assay}.info", enabled)
            view._show_preview()
            output = tmp_path / f"{enabled}.xlsx"
            view._export(output)
            names, rows, data, chart = read_workbook(output)
            assert ("info" in names) is enabled
            if enabled:
                assert [row for row in rows if row[0] == "Source file"] == [
                    ["Source file", path.name, sha256(raw).hexdigest()]
                    for path, raw in zip(source_paths, source_contents)
                ]
                if assay == "binding":
                    assert any("identical repeated half" in " ".join(row) for row in rows)
            else:
                plain_data, plain_chart = data, chart
        assert data == plain_data and chart == plain_chart
        assert previews[0] == previews[1]
    finally:
        dpg.destroy_context()


@pytest.mark.parametrize("assay,cls", ASSAYS)
def test_info_contents_follow_app_language_without_translating_sources(tmp_path, assay, cls):
    from spectrexcel import i18n
    from spectrexcel.assays.export_info import SourceInfo

    previous = i18n.get_language()
    try:
        i18n.set_language("it")
        output = tmp_path / "italian.xlsx"
        source = SourceInfo("Settings", "abc123")
        export(assay, output, info_sources=(source,))
        names, rows, data, chart = read_workbook(output)
        assert names == ["data", "raw", "info"]
        assert ["Fonti", "Nome file", "SHA-256"] in rows
        assert ["Impostazioni", "Valore"] in rows
        assert ["Elaborazione", "Passaggio"] in rows
        assert ["File sorgente", "Settings", "abc123"] in rows
        entries = {row[0]: row[1] for row in rows if len(row) == 2}
        assert entries["Versione di SpectrExcel"] == version("spectrexcel")
        assert entries["Assay"] == {"binding": "binding / titolazione", "spectra": "famiglia di spettri", "kinetics": "cinetiche"}[assay]
        assert entries["Lunghezza d'onda di correzione (nm)"] == "800"
        assert any("Sottrai" in " ".join(row) for row in rows)
        assert not any(row[0] in ("Processing step", "Source file", "Export timestamp", "Reproduction") for row in rows)
        if assay == "binding":
            assert entries["Spettri duplicati rimossi"] == "No"
            assert ["Passaggio di elaborazione", "Rimuovi la colonna della deviazione standard."] in rows
        elif assay == "spectra":
            assert entries["Passo degli spettri nel grafico"] == "2"
        else:
            assert entries["Lunghezza d'onda di lettura (nm)"] == "300"
        i18n.set_language("en")
        english = tmp_path / "english.xlsx"
        export(assay, english, info_sources=(source,))
        en_names, en_rows, en_data, en_chart = read_workbook(english)
        assert en_names == names
        assert ["Sources", "Filename", "SHA-256"] in en_rows
        assert en_data == data and en_chart == chart
    finally:
        i18n.set_language(previous)


def test_disabled_correction_value_follows_app_language(tmp_path):
    from spectrexcel import i18n
    from spectrexcel.assays.export_info import SourceInfo

    previous = i18n.get_language()
    try:
        i18n.set_language("it")
        output = tmp_path / "disabled.xlsx"
        frame = pd.DataFrame({0.0: [1.0, 0.25]}, index=[300, 800])
        export_spectrum_family(frame, Path("input.KD"), output, info_sources=(SourceInfo("input.KD", "abc"),))
        names, rows, data, chart = read_workbook(output)
        assert ["Lunghezza d'onda di correzione (nm)", "Disabilitata"] in rows
    finally:
        i18n.set_language(previous)
