import struct
from xml.etree import ElementTree
from zipfile import ZipFile

import pandas as pd
import pytest

from tests.xml_helpers import required_text

from spectrexcel.assays.parsing import parse_sd_file, parse_txt_file
from spectrexcel.assays.titolazione import (
    binding_chart_spec,
    clean_duplicate_spectra,
    ensure_sample_column,
    export_binding,
)


def test_clean_duplicate_spectra_keeps_single_spectrum():
    dataframe = pd.DataFrame([
        {"#Sample": "sample-1", 190: 0.1, 191: 0.2},
    ])

    cleaned, did_clean = clean_duplicate_spectra(dataframe)

    assert not did_clean
    assert cleaned.equals(dataframe)


def test_clean_duplicate_spectra_removes_matching_halves():
    dataframe = pd.DataFrame([
        {"#Sample": "sample-1", 190: 0.1, 191: 0.2},
        {"#Sample": "sample-2", 190: 0.3, 191: 0.4},
        {"#Sample": "sample-3", 190: 0.1, 191: 0.2},
        {"#Sample": "sample-4", 190: 0.3, 191: 0.4},
    ])

    cleaned, did_clean = clean_duplicate_spectra(dataframe)

    assert did_clean
    assert cleaned.equals(dataframe.head(2))


def test_clean_duplicate_spectra_keeps_odd_number_of_rows():
    dataframe = pd.DataFrame([
        {"#Sample": "sample-1", 190: 0.1, 191: 0.2},
        {"#Sample": "sample-2", 190: 0.3, 191: 0.4},
        {"#Sample": "sample-3", 190: 0.1, 191: 0.2},
    ])

    cleaned, did_clean = clean_duplicate_spectra(dataframe)

    assert not did_clean
    assert cleaned.equals(dataframe)


@pytest.mark.parametrize("second_half", [
    [{"#Sample": "third", 190: 0.1, 191: 0.2}, {"#Sample": "fourth", 190: 0.3, 191: 0.5}],
    [{"#Sample": "third", 190: 0.3, 191: 0.4}, {"#Sample": "fourth", 190: 0.1, 191: 0.2}],
])
def test_clean_duplicate_spectra_keeps_even_nonmatching_halves(second_half):
    dataframe = pd.DataFrame([
        {"#Sample": "first", 190: 0.1, 191: 0.2},
        {"#Sample": "second", 190: 0.3, 191: 0.4},
        *second_half,
    ], index=[10, 20, 30, 40])
    original = dataframe.copy(deep=True)

    cleaned, did_clean = clean_duplicate_spectra(dataframe)

    assert not did_clean
    pd.testing.assert_frame_equal(cleaned, original)
    pd.testing.assert_frame_equal(dataframe, original)


def test_clean_duplicate_spectra_preserves_empty_input():
    dataframe = pd.DataFrame(columns=["#Sample", 190, 191])

    cleaned, did_clean = clean_duplicate_spectra(dataframe)

    assert not did_clean
    pd.testing.assert_frame_equal(cleaned, dataframe)


def test_clean_duplicate_spectra_preserves_input_and_first_half_index():
    dataframe = pd.DataFrame([
        {"#Sample": "first", 190: 0.1, 191: 0.2},
        {"#Sample": "second", 190: 0.3, 191: 0.4},
        {"#Sample": "third", 190: 0.1, 191: 0.2},
        {"#Sample": "fourth", 190: 0.3, 191: 0.4},
    ], index=[10, 20, 30, 40])
    original = dataframe.copy(deep=True)

    cleaned, did_clean = clean_duplicate_spectra(dataframe)

    assert did_clean
    pd.testing.assert_frame_equal(cleaned, original.iloc[:2])
    pd.testing.assert_frame_equal(dataframe, original)


def test_binding_export_keeps_missing_text_absorbance_as_blank_cell(tmp_path):
    source = tmp_path / "missing.txt"
    source.write_text(
        '"WL Result" "#Sample" "<190 nm>" "<191 nm>"\n'
        "0 1 0.5 0.6\n0 2 0.7\n"
    )
    dataframe = parse_txt_file(source)
    original = dataframe.copy(deep=True)
    output = tmp_path / "missing.xlsx"

    export_binding(dataframe, output, 190, 191, 0.0, 1.0)

    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(output) as workbook:
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    assert float(required_text(sheet, ".//s:c[@r='C2']/s:v", ns)) == 0.6
    assert float(required_text(sheet, ".//s:c[@r='B3']/s:v", ns)) == 0.7
    assert sheet.find(".//s:c[@r='C3']/s:v", ns) is None
    pd.testing.assert_frame_equal(dataframe, original)


@pytest.mark.parametrize("variant", ["old", "new"])
def test_binding_export_preserves_generated_sd_labels_and_all_absorbances(tmp_path, variant):
    header = b"(AU)\x00" if variant == "old" else b"(\x00A\x00U\x00)\x00" + bytes(9)
    source = tmp_path / "unlabeled.SD"
    source.write_bytes(
        header + struct.pack("<911d", *([0.25] * 911))
        + header + struct.pack("<911d", *([0.5] * 911))
    )
    dataframe = parse_sd_file(source)
    original = dataframe.copy(deep=True)
    output = tmp_path / "unlabeled.xlsx"

    export_binding(dataframe, output, 190, 1100, 0.0, 1.0)

    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(output) as workbook:
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    assert [int(required_text(sheet, f".//s:c[@r='A{row}']/s:v", ns))
            for row in (2, 3)] == [1, 2]
    for row, expected in [(2, 0.25), (3, 0.5)]:
        values = [float(required_text(cell, "s:v", ns))
                  for cell in sheet.findall(f"s:sheetData/s:row[@r='{row}']/s:c", ns)]
        assert values[1:] == [expected] * 911
    pd.testing.assert_frame_equal(dataframe, original)


@pytest.mark.parametrize("rows", [2, 3])
def test_text_table_without_sample_column_keeps_every_wavelength(tmp_path, rows):
    source = tmp_path / "unlabeled.txt"
    source.write_text(
        '"WL Result" "<190 nm>" "<191 nm>"\n'
        + "".join(f"0 0.{row} 0.{row}5\n" for row in range(1, rows + 1))
    )

    dataframe, cleaned = clean_duplicate_spectra(
        ensure_sample_column(parse_txt_file(source))
    )

    assert not cleaned
    assert list(dataframe["#Sample"]) == list(range(1, rows + 1))
    spec = binding_chart_spec(dataframe, 190, 191, 0.0, 1.0, None)
    assert [series.name for series in spec.series] == [str(row) for row in range(1, rows + 1)]
    assert spec.series[0].x == [190.0, 191.0]
    assert spec.series[0].y == [0.1, 0.15]


def test_ensure_sample_column_keeps_existing_labels():
    dataframe = pd.DataFrame({"#Sample": ["blank", "sample"], "190": [0.1, 0.2]})

    assert ensure_sample_column(dataframe) is dataframe
    assert list(dataframe["#Sample"]) == ["blank", "sample"]


def test_binding_chart_ranges_end_at_last_wavelength_column(tmp_path):
    dataframe = pd.DataFrame(
        {"#Sample": [1, 2], 190: [0.1, 0.2], 191: [0.3, 0.4], 192: [0.5, 0.6]}
    )
    output = tmp_path / "ranges.xlsx"

    export_binding(dataframe, output, 190, 192, 0.0, 1.0, 192)

    ns = {"c": "http://schemas.openxmlformats.org/drawingml/2006/chart"}
    with ZipFile(output) as workbook:
        charts = {
            sheet: ElementTree.fromstring(workbook.read(f"xl/charts/chart{number}.xml"))
            for number, sheet in ((1, "data"), (2, "raw"))
        }
    for sheet, chart in charts.items():
        assert [node.text for node in chart.findall(".//c:f", ns)] == [
            f"{sheet}!$B$1:$D$1", f"{sheet}!$B$2:$D$2",
            f"{sheet}!$B$1:$D$1", f"{sheet}!$B$3:$D$3",
        ]
