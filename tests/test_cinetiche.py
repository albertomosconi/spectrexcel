from xml.etree import ElementTree
from zipfile import ZipFile

import pandas as pd
import dearpygui.dearpygui as dpg

from spectrexcel.assays.cinetiche import Cinetiche, export_kinetics
from spectrexcel.dpi import DisplayScale


def test_reorder_popup_builds():
    dpg.create_context()
    dpg.create_viewport()
    try:
        assay = Cinetiche(
            lambda _message: None,
            lambda *_args: None,
            None,
            DisplayScale(),
        )
        assay.datasets = [
            ("sample-1", pd.DataFrame()),
            ("sample-2", pd.DataFrame()),
        ]

        assay._show_reorder()

        assert dpg.does_item_exist("kinetics.reorder.modal")
        modal_config = dpg.get_item_configuration("kinetics.reorder.modal")
        assert modal_config["no_move"]
        assert modal_config["no_resize"]
        assay._move_dataset(None, None, (0, 1))
        assert dpg.does_item_exist("kinetics.reorder.modal")
        assert dpg.get_value("kinetics.reorder.filename.0") == "sample-2"
    finally:
        dpg.destroy_context()


def test_export_kinetics_preserves_dataset_and_chart_order(tmp_path):
    spectra = pd.DataFrame({0: [0.2, 0.1], 10: [0.3, 0.1]}, index=[300, 800])
    output_path = tmp_path / "kinetics.xlsx"

    export_kinetics(
        [("sample-10", spectra), ("sample-2", spectra)],
        output_path,
        reading_wavelength=300,
        correction_wavelength=800,
    )

    spreadsheet_ns = {
        "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    }
    chart_ns = {
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    }
    with ZipFile(output_path) as workbook:
        shared_strings = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
        strings = ["".join(item.itertext()) for item in shared_strings]
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
        chart = ElementTree.fromstring(workbook.read("xl/charts/chart1.xml"))

    def cell_string(reference: str) -> str:
        cell = sheet.find(f".//s:c[@r='{reference}']", spreadsheet_ns)
        assert cell is not None
        value = cell.find("s:v", spreadsheet_ns)
        assert value is not None and value.text is not None
        return strings[int(value.text)]

    assert [cell_string("B2"), cell_string("C2")] == ["sample-10", "sample-2"]

    series = chart.findall(".//c:ser", chart_ns)
    assert [
        item.findtext("c:tx/c:strRef/c:f", namespaces=chart_ns) for item in series
    ] == ["data!$B$2", "data!$C$2"]
    assert all(
        item.find("c:spPr/a:ln/a:solidFill", chart_ns) is None for item in series
    )


def test_export_kinetics_zeroes_time_axis(tmp_path):
    spectra = pd.DataFrame({8.4: [0.2, 0.1], 15.7: [0.3, 0.1]}, index=[300, 800])
    output_path = tmp_path / "kinetics.xlsx"

    export_kinetics(
        [("sample-1", spectra)],
        output_path,
        reading_wavelength=300,
        correction_wavelength=800,
    )

    spreadsheet_ns = {
        "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    }
    chart_ns = {
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    }
    with ZipFile(output_path) as workbook:
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
        chart = ElementTree.fromstring(workbook.read("xl/charts/chart1.xml"))

    def cell_number(reference: str) -> float:
        cell = sheet.find(f".//s:c[@r='{reference}']", spreadsheet_ns)
        assert cell is not None
        value = cell.find("s:v", spreadsheet_ns)
        assert value is not None and value.text is not None
        return float(value.text)

    assert cell_number("A3") == 0.0
    assert cell_number("A4") == 15.7 - 8.4

    def axis_position(axis) -> str:
        position = axis.find("c:axPos", chart_ns)
        assert position is not None
        return position.get("val")

    x_axis = next(
        axis
        for axis in chart.findall(".//c:valAx", chart_ns)
        if axis_position(axis) == "b"
    )
    scaling = x_axis.find("c:scaling", chart_ns)
    assert scaling is not None
    minimum = scaling.find("c:min", chart_ns)
    maximum = scaling.find("c:max", chart_ns)
    assert minimum is not None and maximum is not None
    assert float(minimum.get("val")) == 0.0
    assert float(maximum.get("val")) == 15.7 - 8.4
