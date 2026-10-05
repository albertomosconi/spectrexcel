import dearpygui.dearpygui as dpg
import pytest
import os
import subprocess
import sys
from pathlib import Path

from spectrexcel.assays.cinetiche import Cinetiche
from spectrexcel.assays.famiglia_di_spettri import FamigliaDiSpettri
from spectrexcel.assays.titolazione import BindingTitolazione
from spectrexcel.dpi import DisplayScale


@pytest.fixture
def layout_context():
    dpg.create_context()
    dpg.create_viewport(width=720, height=520)
    dpg.add_theme(tag="theme.accent")
    dpg.add_theme(tag="theme.muted")
    try:
        yield
    finally:
        dpg.destroy_context()


@pytest.mark.parametrize("value", [None, "unknown", [], 42])
def test_invalid_layout_defaults(value):
    from spectrexcel.layouts import PARAMETERS_ONLY, resolve_layout
    assert resolve_layout(value) == PARAMETERS_ONLY


@pytest.mark.parametrize("cls,tag", [
    (BindingTitolazione, "binding.x_min"),
    (Cinetiche, "kinetics.reading"),
    (FamigliaDiSpettri, "spectra.correction"),
])
def test_layout_change_keeps_widget_identity_and_button_state(layout_context, cls, tag):
    from spectrexcel.layouts import PARAMETERS_ONLY, PARAMETERS_PREVIEW
    view = cls(lambda message: None, lambda *args: None, {}, DisplayScale())
    view.mount(dpg.add_window(), PARAMETERS_ONLY)
    original_id = dpg.get_alias_id(tag)
    dpg.set_value(tag, 333)
    for mode in (PARAMETERS_PREVIEW, PARAMETERS_ONLY, PARAMETERS_PREVIEW):
        view.apply_layout(mode)
        assert dpg.get_alias_id(tag) == original_id
        assert dpg.get_value(tag) == 333
        config = dpg.get_item_configuration(view.workflow_controls.preview)
        assert config["show"] == (mode == PARAMETERS_ONLY)
        assert not config["enabled"]
        for row in view._layout_rows:
            assert dpg.get_item_configuration(row)["horizontal"] == (mode == PARAMETERS_ONLY)


@pytest.mark.parametrize("factor", [1.0, 2.0])
@pytest.mark.parametrize("cls", [BindingTitolazione, Cinetiche, FamigliaDiSpettri])
def test_two_panes_fit_minimum_size_and_wrap_filename(layout_context, monkeypatch, factor, cls):
    from spectrexcel.layouts import PARAMETERS_ONLY, PARAMETERS_PREVIEW
    scale = DisplayScale(factor)
    parent = dpg.add_window()
    monkeypatch.setattr(dpg, "get_item_rect_size", lambda item: (scale.pixels(684), scale.pixels(270)))
    view = cls(lambda message: None, lambda *args: None, {}, scale)
    view.mount(parent, PARAMETERS_PREVIEW)
    view.maintain_layout()
    panes = view._assay_layout
    left = dpg.get_item_configuration(panes.parameters)
    right = dpg.get_item_configuration(panes.preview)
    assert left["width"] == right["width"]
    assert left["width"] * 2 + scale.pixels(8) <= scale.pixels(684)
    assert left["height"] > 0 and right["height"] > 0
    assert right["show"]
    assert not left["no_scrollbar"]
    status = dpg.get_item_configuration(view.workflow_controls.status)
    assert 0 < status["wrap"] < left["width"]
    view.apply_layout(PARAMETERS_ONLY)
    assert not dpg.get_item_configuration(panes.preview)["show"]
    assert dpg.get_item_configuration(panes.parameters)["width"] == scale.pixels(684)
    assert dpg.get_item_configuration(view.workflow_controls.status)["wrap"] == -1


def test_layout_switch_closes_existing_modal(layout_context, monkeypatch):
    from spectrexcel.layouts import PARAMETERS_ONLY, PARAMETERS_PREVIEW
    from spectrexcel.charts import ChartSpec, ChartSeries
    monkeypatch.setattr(dpg, "get_viewport_client_width", lambda: 720)
    monkeypatch.setattr(dpg, "get_viewport_client_height", lambda: 520)
    view = BindingTitolazione(lambda message: None, lambda *args: None, {}, DisplayScale())
    view.mount(dpg.add_window(), PARAMETERS_ONLY)
    view.show_chart_preview(ChartSpec("x", "y", (0, 1), (0, 1),
                            (ChartSeries("one", [0, 1], [0.1, 0.2]),)))
    view.apply_layout(PARAMETERS_PREVIEW)
    assert not dpg.does_item_exist("chart.preview.modal")


@pytest.mark.skipif(os.environ.get("SPECTREXCEL_GUI_TESTS") != "1",
                    reason="Opt-in rendered checks require a desktop display")
@pytest.mark.parametrize("factor", [1, 2])
@pytest.mark.parametrize("language", ["en", "it"])
def test_rendered_layouts_fill_content_and_keep_controls_inside_pane(tmp_path, factor, language):
    subprocess.run(
        [sys.executable, "-c",
         "import runpy,sys; from pathlib import Path; "
         "runpy.run_path(sys.argv[1])['_check_rendered_layouts']"
         "(Path(sys.argv[2]),int(sys.argv[3]),sys.argv[4])",
         __file__, str(tmp_path), str(factor), language],
        check=True, timeout=60,
    )


def _check_rendered_layouts(tmp_path, factor, language):
    import time
    import pandas as pd
    import spectrexcel.settings as settings_module
    from spectrexcel.main import ASSAYS, SpectrExcelApp
    from spectrexcel.settings import Settings
    from spectrexcel.layouts import LAYOUT_LABELS, PARAMETERS_ONLY, PARAMETERS_PREVIEW
    from spectrexcel.i18n import _

    settings_module.user_config_path = lambda *args: tmp_path
    settings = Settings()
    settings.set("main/language", language)
    settings.set("main/theme", "Light")
    scale = DisplayScale(factor)
    dpg.create_context()
    dpg.create_viewport(title="SpectrExcel layout verification", width=1000 * factor,
                        height=700 * factor, vsync=False)
    app = SpectrExcelApp("test", scale)
    app._find_update = lambda: None
    app._find_citation = lambda: None

    def frames():
        deadline = time.monotonic() + 5
        for _frame in range(12):
            app.process_results()
            app.maintain_assay()
            dpg.render_dearpygui_frame()
        while app.has_running_tasks() or app.assay_view._preview_running:
            assert time.monotonic() < deadline
            app.process_results()
            app.maintain_assay()
            dpg.render_dearpygui_frame()

    try:
        app.build()
        dpg.setup_dearpygui()
        dpg.show_viewport()
        for index in range(len(ASSAYS)):
            app._load_assay(index)
            view = app.assay_view
            if index == 0:
                view.dataframe = pd.DataFrame({"#Sample": ["one"], 300: [1.0], 800: [0.25]})
            else:
                frame = pd.DataFrame({0: [1.0, 0.25], 10: [0.5, 0.25]}, index=[300, 800])
                if index == 1:
                    view.datasets = [("long filename " * 6 + str(i), frame) for i in range(8)]
                else:
                    view.dataframe = frame
            view.input_path = Path("long filename " * 10 + ".KD")
            dpg.set_value(view.workflow_controls.status, view.input_path.name)
            for width, height in ((720, 520), (1000, 700)):
                dpg.configure_viewport(0, width=width * factor, height=height * factor)
                app._layout_changed(None, _(LAYOUT_LABELS[PARAMETERS_PREVIEW]))
                frames()
                panes = view._assay_layout
                available = dpg.get_item_state("assay.content")["content_region_avail"]
                left = dpg.get_item_rect_size(panes.parameters)
                right = dpg.get_item_rect_size(panes.preview)
                assert abs(left[0] + right[0] + scale.pixels(8) - available[0]) <= 2
                assert abs(right[1] - available[1]) <= 2
                assert dpg.get_y_scroll_max("assay.content") == 0
                assert view._embedded_renderer.plot is not None
                for tag, logical_width, label, heading in view._layout_fields:
                    state = dpg.get_item_state(tag)
                    assert state["pos"][0] + state["rect_size"][0] <= left[0] - scale.pixels(10)
                app._layout_changed(None, _(LAYOUT_LABELS[PARAMETERS_ONLY]))
                frames()
                assert dpg.get_item_rect_size(panes.parameters)[0] == available[0]
    finally:
        app.shutdown()
        dpg.destroy_context()
