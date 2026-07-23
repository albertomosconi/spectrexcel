import dearpygui.dearpygui as dpg
import pytest

import spectrexcel.main as main_module
from spectrexcel.dpi import DisplayScale
from spectrexcel.i18n import TRANSLATIONS_IT
from spectrexcel.i18n import _, get_language, set_language
from spectrexcel.main import ASSAYS, THEME_COLORS, SpectrExcelApp


def test_assays_have_translated_descriptions():
    assert ASSAYS
    assert TRANSLATIONS_IT["About assay"].strip()
    for assay in ASSAYS:
        assert assay.description.strip()
        assert TRANSLATIONS_IT[assay.description].strip()


@pytest.fixture
def dpg_context():
    previous_language = get_language()
    dpg.create_context()
    dpg.create_viewport(width=800, height=520)
    try:
        yield
    finally:
        dpg.destroy_context()
        set_language(previous_language)


def test_build_adds_question_mark_assay_info_button(
    dpg_context, monkeypatch, tmp_path
):
    monkeypatch.setattr("spectrexcel.settings.user_config_path", lambda *_args: tmp_path)
    monkeypatch.setattr(SpectrExcelApp, "submit", lambda *_args: None)
    set_language("en")
    app = SpectrExcelApp("test", DisplayScale())
    try:
        app.build()

        assert dpg.get_item_configuration("main.assay_info")["label"] == "?"
        assert dpg.get_value("main.assay_info.tooltip.text") == "About assay"
    finally:
        app.executor.shutdown(wait=True)


def test_disabled_button_palettes_are_muted_and_do_not_react_to_pointer_state():
    disabled_colors = main_module.DISABLED_BUTTON_COLORS
    assert set(disabled_colors) == {"Light", "Dark"}
    assert disabled_colors["Light"] != disabled_colors["Dark"]
    for name, colors in disabled_colors.items():
        assert colors["Text"] != THEME_COLORS[name]["Text"]
        assert colors["Button"] != THEME_COLORS[name]["Button"]
        assert colors["Button"] == colors["ButtonHovered"] == colors["ButtonActive"]


def test_build_registers_one_disabled_button_component_per_theme(
    dpg_context, monkeypatch, tmp_path
):
    monkeypatch.setattr("spectrexcel.settings.user_config_path", lambda *_args: tmp_path)
    monkeypatch.setattr(SpectrExcelApp, "submit", lambda *_args: None)
    app = SpectrExcelApp("test", DisplayScale())
    try:
        app.build()

        for name in ("Light", "Dark"):
            components = dpg.get_item_children(f"theme.{name.lower()}", 1)
            disabled_buttons = [
                component
                for component in components
                if dpg.get_item_configuration(component)["item_type"] == dpg.mvButton
                and not dpg.get_item_configuration(component)["enabled_state"]
            ]
            assert len(disabled_buttons) == 1
    finally:
        app.executor.shutdown(wait=True)


def test_assay_info_modal_uses_selected_assay_and_is_locked(
    dpg_context, monkeypatch
):
    monkeypatch.setattr(dpg, "get_viewport_client_width", lambda: 800)
    monkeypatch.setattr(dpg, "get_viewport_client_height", lambda: 520)
    set_language("en")
    app = SpectrExcelApp.__new__(SpectrExcelApp)
    app.display_scale = DisplayScale()
    app.selected_assay_index = 1

    app._show_assay_info()

    assay = ASSAYS[1]
    config = dpg.get_item_configuration("assay.info.modal")
    assert dpg.get_item_label("assay.info.modal") == _(assay.name)
    assert dpg.get_value("assay.info.description") == _(assay.description)
    assert config["modal"]
    assert config["no_move"]
    assert config["no_resize"]
    assert config["no_collapse"]
    assert config["no_close"]
