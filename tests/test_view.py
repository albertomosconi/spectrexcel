from pathlib import Path

from spectrexcel.assays.view import AssayView
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
