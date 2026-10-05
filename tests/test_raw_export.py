from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pandas as pd
import pytest

from spectrexcel.assays.cinetiche import export_kinetics
from spectrexcel.assays.export_info import SourceInfo
from spectrexcel.assays.famiglia_di_spettri import export_spectrum_family
from spectrexcel.assays.titolazione import export_binding


NS = {
    "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
}


def export(assay, path, correction=800, info=False, different_times=False):
    kwargs = {"info_sources": (SourceInfo("input.KD", "abc"),) if info else None}
    spectra = pd.DataFrame({5.0: [3.0, 0.25], 15.0: [-0.5, 0.1]}, index=[300, 800])
    original = spectra.copy(deep=True)
    if assay == "binding":
        frame = pd.DataFrame({"#Sample": ["first", "second"], "Std.Dev.": [0.1, 0.2],
                              "300": [3.0, -0.5], "800": [0.25, 0.1]})
        before = frame.copy(deep=True)
        export_binding(frame, path, 200, 900, -1.0, 1.0, correction, **kwargs)
        pd.testing.assert_frame_equal(frame, before)
    elif assay == "spectra":
        export_spectrum_family(spectra, Path("input.KD"), path, correction, **kwargs)
    else:
        other = pd.DataFrame({10.0: [1.5, 0.2], 23.0: [2.0, 0.3], 31.0: [2.5, 0.4]},
                             index=[300, 800]) if different_times else spectra.copy()
        other_before = other.copy(deep=True)
        export_kinetics([("first", spectra), ("second", other)], path, 300, correction, **kwargs)
        pd.testing.assert_frame_equal(other, other_before)
    pd.testing.assert_frame_equal(spectra, original)


def cell_values(sheet, refs):
    return [float(sheet.findtext(f".//s:c[@r='{ref}']/s:v", namespaces=NS)) for ref in refs]


@pytest.mark.parametrize("assay", ["binding", "spectra", "kinetics"])
@pytest.mark.parametrize("info", [False, True])
def test_corrected_export_preserves_raw_values_and_chart_in_second_sheet(tmp_path, assay, info):
    path = tmp_path / "export.xlsx"
    export(assay, path, info=info)

    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        names = [sheet.get("name") for sheet in workbook.findall("s:sheets/s:sheet", NS)]
        assert names == ["data", "raw"] + (["info"] if info else [])
        raw = ET.fromstring(archive.read("xl/worksheets/sheet2.xml"))
        data = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        if assay == "binding":
            refs, values = ["B2", "C2", "B3", "C3"], [3.0, 0.25, -0.5, 0.1]
            corrected = [2.75, 0.0, -0.6, 0.0]
        elif assay == "spectra":
            refs, values = ["B2", "C2", "B3", "C3"], [3.0, -0.5, 0.25, 0.1]
            corrected = [2.75, -0.6, 0.0, 0.0]
        else:
            refs, values = ["A3", "A4", "B3", "B4", "C3", "C4"], [0, 10, 3.0, -0.5, 3.0, -0.5]
            corrected = [0, 10, 2.75, -0.6, 2.75, -0.6]
        assert cell_values(raw, refs) == pytest.approx(values)
        assert cell_values(data, refs) == pytest.approx(corrected)
        assert raw.find("s:drawing", NS) is not None
        chart = ET.fromstring(archive.read("xl/charts/chart2.xml"))
        formulas = [element.text for element in chart.findall(".//c:f", NS)]
        assert formulas and all(formula.startswith("raw!") for formula in formulas)
        # Raw values exceed configured corrected-chart range; none should be clipped.
        y_axis = chart.findall(".//c:valAx", NS)[1]
        minimum = y_axis.find("c:scaling/c:min", NS)
        maximum = y_axis.find("c:scaling/c:max", NS)
        assert minimum is None or float(minimum.get("val")) <= -0.5
        assert maximum is None or float(maximum.get("val")) >= 3.0


@pytest.mark.parametrize("assay", ["binding", "spectra"])
@pytest.mark.parametrize("info", [False, True])
def test_disabled_correction_does_not_add_raw_sheet(tmp_path, assay, info):
    path = tmp_path / "export.xlsx"
    export(assay, path, correction=None, info=info)
    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        assert [sheet.get("name") for sheet in workbook.findall("s:sheets/s:sheet", NS)] == (
            ["data", "info"] if info else ["data"]
        )
        assert "xl/charts/chart2.xml" not in archive.namelist()


def test_raw_kinetics_preserves_independent_time_grids(tmp_path):
    path = tmp_path / "kinetics.xlsx"
    export("kinetics", path, different_times=True)
    with ZipFile(path) as archive:
        raw = ET.fromstring(archive.read("xl/worksheets/sheet2.xml"))
        assert cell_values(raw, ["A3", "A4", "B3", "B4", "C3", "C4", "C5", "D3", "D4", "D5"]) == [
            0, 10, 3.0, -0.5, 0, 13, 21, 1.5, 2.0, 2.5,
        ]
        chart = ET.fromstring(archive.read("xl/charts/chart2.xml"))
        assert [node.text for node in chart.findall(".//c:xVal/c:numRef/c:f", NS)] == [
            "raw!$A$3:$A$4", "raw!$C$3:$C$5",
        ]
