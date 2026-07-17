from pathlib import Path

import pandas as pd

from spectrexcel.assays.shared import AssayView, clean_duplicate_spectra
from spectrexcel.dpi import DisplayScale


def assay_view():
    return AssayView(lambda _message: None, lambda *_args: None, None, DisplayScale())


def test_open_file_dialog_returns_native_selections(monkeypatch, tmp_path):
    selected = [str(tmp_path / "one.KD"), "", str(tmp_path / "two.KD")]
    monkeypatch.setattr(
        "spectrexcel.native_dialogs.open_files", lambda *_args: selected
    )
    received = []

    assay_view().open_file_dialog(
        title="Open",
        callback=received.extend,
        filters={"Kinetic data files": ["*.KD", "*.kd"]},
        default_path=str(tmp_path),
        multiple=True,
    )

    assert received == [Path(selected[0]), Path(selected[2])]


def test_save_file_dialog_adds_xlsx_suffix(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "spectrexcel.native_dialogs.save_file", lambda *_args: str(tmp_path / "result")
    )
    received = []

    assay_view().save_file_dialog(
        title="Save",
        callback=received.append,
        default_path=str(tmp_path),
        default_filename="result.xlsx",
    )

    assert received == [tmp_path / "result.xlsx"]


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
