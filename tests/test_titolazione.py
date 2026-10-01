import struct
from xml.etree import ElementTree
from zipfile import ZipFile

import pandas as pd
import pytest

from spectrexcel.assays.parsing import parse_sd_file, parse_txt_file
from spectrexcel.assays.titolazione import clean_duplicate_spectra, export_binding


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
    assert float(sheet.findtext(".//s:c[@r='C2']/s:v", namespaces=ns)) == 0.6
    assert float(sheet.findtext(".//s:c[@r='B3']/s:v", namespaces=ns)) == 0.7
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
    assert [int(sheet.findtext(f".//s:c[@r='A{row}']/s:v", namespaces=ns))
            for row in (2, 3)] == [1, 2]
    for row, expected in [(2, 0.25), (3, 0.5)]:
        values = [float(cell.findtext("s:v", namespaces=ns))
                  for cell in sheet.findall(f"s:sheetData/s:row[@r='{row}']/s:c", ns)]
        assert values[1:] == [expected] * 911
    pd.testing.assert_frame_equal(dataframe, original)
