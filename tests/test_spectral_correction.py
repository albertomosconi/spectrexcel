from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

import dearpygui.dearpygui as dpg
import pandas as pd
import pytest

from spectrexcel.assays.famiglia_di_spettri import (
    FamigliaDiSpettri,
    export_spectrum_family,
)
from spectrexcel.assays.titolazione import BindingTitolazione, export_binding
from spectrexcel.dpi import DisplayScale
from tests.xml_helpers import required_attribute, required_text


def spectra(assay, text_columns=False):
    if assay == "binding":
        return pd.DataFrame({
            "#Sample": ["first", "second"],
            "Std.Dev.": [0.1, 0.2],
            "300" if text_columns else 300: [1.0, 0.25],
            "800" if text_columns else 800: [0.25, 0.5],
        })
    return pd.DataFrame({0.0: [1.0, 0.25], 10.0: [0.25, 0.5]}, index=[300, 800])


def export(assay, dataframe, path, **kwargs):
    if assay == "binding":
        export_binding(dataframe, path, 200, 900, -1.0, 2.0, **kwargs)
    else:
        export_spectrum_family(dataframe, Path("input.KD"), path, **kwargs)


def workbook_values(path, references):
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(path) as workbook:
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    return [float(required_text(sheet, f".//s:c[@r='{ref}']/s:v", ns)) for ref in references]


@pytest.mark.parametrize("assay,text_columns", [("binding", False), ("binding", True), ("spectra", False)])
def test_export_subtracts_each_spectrums_own_baseline(tmp_path, assay, text_columns):
    dataframe = spectra(assay, text_columns)
    original = dataframe.copy(deep=True)
    path = tmp_path / "corrected.xlsx"

    export(assay, dataframe, path, correction_wavelength=800)

    refs = ["B2", "C2", "B3", "C3"]
    expected = [0.75, 0.0, -0.25, 0.0] if assay == "binding" else [0.75, -0.25, 0.0, 0.0]
    assert workbook_values(path, refs) == pytest.approx(expected)
    pd.testing.assert_frame_equal(dataframe, original)


@pytest.mark.parametrize("assay", ["binding", "spectra"])
def test_export_without_correction_preserves_absorbances(tmp_path, assay):
    path = tmp_path / "raw.xlsx"
    export(assay, spectra(assay), path)
    expected = [1.0, 0.25, 0.25, 0.5]
    assert workbook_values(path, ["B2", "C2", "B3", "C3"]) == expected


@pytest.mark.parametrize("assay", ["binding", "spectra"])
def test_export_rejects_missing_correction_wavelength(tmp_path, assay):
    path = tmp_path / "missing.xlsx"
    with pytest.raises(ValueError, match="801"):
        export(assay, spectra(assay), path, correction_wavelength=801)
    assert not path.exists()


@pytest.mark.parametrize("assay", ["binding", "spectra"])
@pytest.mark.parametrize("enabled", [False, True])
def test_preview_and_ui_export_apply_selected_correction(monkeypatch, tmp_path, assay, enabled):
    values = {
        f"{assay}.info": False,
        f"{assay}.correction_enabled": enabled,
        f"{assay}.correction": 800,
        "binding.x_min": 200, "binding.x_max": 900,
        "binding.y_min": -1.0, "binding.y_max": 2.0,
    }
    monkeypatch.setattr(dpg, "get_value", values.__getitem__)
    saved = {}

    class Settings:
        def set(self, key, value):
            saved[key] = value

    cls = BindingTitolazione if assay == "binding" else FamigliaDiSpettri
    view = cls(lambda message: None, lambda *args: None, Settings(), DisplayScale())
    view.dataframe = spectra(assay)
    view.input_path = Path("input.KD")
    original = view.dataframe.copy(deep=True)
    previews = []
    monkeypatch.setattr(view, "show_chart_preview", previews.append)
    # Execute real export task without desktop busy-state widgets.
    monkeypatch.setattr(view, "submit_export", lambda task: task())

    view._show_preview()
    path = tmp_path / "ui.xlsx"
    view._export(path)

    assert previews[0].series[0].y == ([0.75, 0.0] if enabled else [1.0, 0.25])
    if assay == "binding":
        assert previews[0].series[1].y == ([-0.25, 0.0] if enabled else [0.25, 0.5])
    refs = ["B2", "C2"] if assay == "binding" else ["B2", "B3"]
    assert workbook_values(path, refs) == previews[0].series[0].y
    prefix = "titolazione" if assay == "binding" else "famiglia_di_spettri"
    assert saved[f"{prefix}/correction_enabled"] is enabled
    assert saved[f"{prefix}/wl_corr"] == 800
    pd.testing.assert_frame_equal(view.dataframe, original)


@pytest.mark.parametrize("assay", ["binding", "spectra"])
def test_preview_logs_missing_correction_instead_of_showing_chart(monkeypatch, assay):
    values = {
        f"{assay}.correction_enabled": True, f"{assay}.correction": 801,
        "binding.x_min": 200, "binding.x_max": 900,
        "binding.y_min": -1.0, "binding.y_max": 2.0,
    }
    monkeypatch.setattr(dpg, "get_value", values.__getitem__)
    messages, previews = [], []
    cls = BindingTitolazione if assay == "binding" else FamigliaDiSpettri
    view = cls(messages.append, lambda *args: None, None, DisplayScale())
    view.dataframe, view.input_path = spectra(assay), Path("input.KD")
    monkeypatch.setattr(view, "show_chart_preview", previews.append)

    view._show_preview()

    assert not previews
    assert len(messages) == 1 and "801" in messages[0]


@pytest.mark.parametrize("assay", ["binding", "spectra"])
@pytest.mark.parametrize("remembered", [False, True])
def test_correction_controls_default_off_and_restore_preferences(assay, remembered):
    prefix = "titolazione" if assay == "binding" else "famiglia_di_spettri"
    settings = {
        f"{prefix}/correction_enabled": True,
        f"{prefix}/wl_corr": 700,
    } if remembered else {}
    cls = BindingTitolazione if assay == "binding" else FamigliaDiSpettri
    dpg.create_context()
    try:
        dpg.add_theme(tag="theme.accent")
        dpg.add_theme(tag="theme.muted")
        parent = dpg.add_window()
        view = cls(lambda message: None, lambda *args: None, settings, DisplayScale())
        view.build(parent)

        assert dpg.get_value(f"{assay}.correction_enabled") is remembered
        assert dpg.get_value(f"{assay}.correction") == (700 if remembered else 800)
        config = dpg.get_item_configuration(f"{assay}.correction")
        assert config["min_value"] == 190 and config["max_value"] == 1100
        assert config["min_clamped"] and config["max_clamped"]
        assert config["show"] is remembered
        assert config["label"]
        row = dpg.get_item_parent(f"{assay}.correction")
        assert row is not None
        assert dpg.get_item_parent(f"{assay}.correction_enabled") == row
        assert dpg.get_item_configuration(row)["horizontal"]

        callback = dpg.get_item_callback(f"{assay}.correction_enabled")
        assert callback is not None
        for enabled in (True, False, True):
            dpg.set_value(f"{assay}.correction_enabled", enabled)
            callback(f"{assay}.correction_enabled", enabled)
            assert dpg.get_item_configuration(f"{assay}.correction")["show"] is enabled
            assert dpg.get_value(f"{assay}.correction") == (700 if remembered else 800)
    finally:
        dpg.destroy_context()


@pytest.mark.parametrize("absorbances,expected_limits", [([0.25, 0.5], (-0.25, 0.0)), ([0.5, 0.5], (0.0, 1.0))])
def test_corrected_family_chart_shows_negative_and_flat_spectra(
    monkeypatch, tmp_path, absorbances, expected_limits
):
    dataframe = pd.DataFrame({0.0: absorbances}, index=[300, 800])
    path = tmp_path / "family.xlsx"
    export_spectrum_family(dataframe, Path("input.KD"), path, correction_wavelength=800)
    ns = {"c": "http://schemas.openxmlformats.org/drawingml/2006/chart"}
    with ZipFile(path) as workbook:
        chart = ElementTree.fromstring(workbook.read("xl/charts/chart1.xml"))
    axis = next(axis for axis in chart.findall(".//c:valAx", ns)
                if required_attribute(axis.find("c:axPos", ns), "val") == "l")
    bounds = tuple(float(required_attribute(axis.find(f"c:scaling/c:{name}", ns), "val"))
                   for name in ("min", "max"))
    assert bounds == expected_limits

    values = {"spectra.correction_enabled": True, "spectra.correction": 800}
    monkeypatch.setattr(dpg, "get_value", values.__getitem__)
    view = FamigliaDiSpettri(lambda message: None, lambda *args: None, None, DisplayScale())
    view.dataframe, view.input_path = dataframe, Path("input.KD")
    previews = []
    monkeypatch.setattr(view, "show_chart_preview", previews.append)
    view._show_preview()
    assert previews[0].y_limits == expected_limits
