import os
import subprocess
import sys
from pathlib import Path

import dearpygui.dearpygui as dpg
import pytest
from packaging.version import Version

import spectrexcel.settings as settings_module
from spectrexcel.assays.cinetiche import Cinetiche
from spectrexcel.assays.view import AssayView, ChartSpec
from spectrexcel.dpi import DisplayScale
from spectrexcel.main import SpectrExcelApp
from spectrexcel.updater import ReleaseAsset, UpdateRelease


@pytest.fixture
def viewport(monkeypatch):
    size = [640, 400]
    dpg.create_context()
    dpg.create_viewport(width=640, height=400)
    monkeypatch.setattr(dpg, "get_viewport_client_width", lambda: size[0])
    monkeypatch.setattr(dpg, "get_viewport_client_height", lambda: size[1])
    try:
        yield size
    finally:
        dpg.destroy_context()


def open_dialog(kind, scale, *, long_content=False):
    app = SpectrExcelApp.__new__(SpectrExcelApp)
    app.display_scale = scale
    app.selected_assay_index = 0
    app.theme_preference = "System"
    app.language = "en"
    view = AssayView(lambda _message: None, lambda *_args: None, None, scale)
    if kind == "chart.preview.modal":
        view.show_chart_preview(ChartSpec("x", "y", (0, 1), (0, 1), ()))
    elif kind == "save.overwrite":
        view._confirm_overwrite(Path("result.xlsx"), lambda _path: None)
    elif kind == "settings.modal":
        app._show_settings()
    elif kind == "assay.info.modal":
        app._show_assay_info()
    elif kind == "kinetics.reorder.modal":
        view = Cinetiche(lambda _message: None, lambda *_args: None, None, scale)
        prefix = "long file name " * 20 if long_content else "file"
        view.datasets = [(f"{prefix}{index}.KD", None) for index in range(20)]
        view._show_reorder()
    else:
        app._show_update_confirmation(UpdateRelease(
            tag="v9.0.0", version=Version("9.0.0"),
            asset=ReleaseAsset("app", "https://example/app"),
            notes="## Features\n- " + ("Long release note " * 50 if long_content else "New feature"),
        ))


DIALOGS = [
    "chart.preview.modal", "save.overwrite", "settings.modal",
    "assay.info.modal", "kinetics.reorder.modal", "update.modal",
]


@pytest.mark.parametrize("kind", DIALOGS)
@pytest.mark.parametrize("factor", [1, 2])
def test_dialog_fits_viewport(viewport, kind, factor):
    open_dialog(kind, DisplayScale(factor))
    config = dpg.get_item_configuration(kind)
    x, y = dpg.get_item_pos(kind)
    assert 0 < config["width"] <= 640
    assert 0 < config["height"] <= 400
    assert 0 <= x <= 640 - config["width"]
    assert 0 <= y <= 400 - config["height"]


@pytest.mark.parametrize("kind", DIALOGS)
def test_dialog_actions_outside_scrollable_body(viewport, kind):
    open_dialog(kind, DisplayScale())
    children = dpg.get_item_children(kind, 1)
    bodies = [
        item for item in children
        if dpg.get_item_info(item)["type"] == "mvAppItemType::mvChildWindow"
    ]
    assert len(bodies) == 1
    assert dpg.get_item_configuration(bodies[0])["height"] < 0
    assert any(
        dpg.get_item_info(item)["type"] == "mvAppItemType::mvGroup"
        for item in children
    )


def test_open_dialog_refits_on_resize_and_restores_preferred_size(viewport):
    from spectrexcel.dialogs import maintain_dialogs

    open_dialog("chart.preview.modal", DisplayScale())
    viewport[:] = [500, 300]
    maintain_dialogs()
    config = dpg.get_item_configuration("chart.preview.modal")
    assert config["width"] <= 500
    assert config["height"] <= 300
    viewport[:] = [1000, 800]
    maintain_dialogs()
    config = dpg.get_item_configuration("chart.preview.modal")
    assert (config["width"], config["height"]) == (760, 600)


def test_reorder_filenames_leave_room_for_move_buttons(viewport):
    from spectrexcel.dialogs import maintain_dialogs

    viewport[:] = [500, 400]
    open_dialog("kinetics.reorder.modal", DisplayScale())
    config = dpg.get_item_configuration("kinetics.reorder.filename.0")
    assert 0 < config["wrap"] <= 240
    viewport[:] = [1000, 800]
    maintain_dialogs()
    assert dpg.get_item_configuration("kinetics.reorder.filename.0")["wrap"] == 312


def test_preview_plot_fills_available_body_not_preferred_dialog_height(viewport):
    open_dialog("chart.preview.modal", DisplayScale())
    plot = dpg.get_item_children("chart.preview.modal.body", 1)[0]
    assert dpg.get_item_configuration(plot)["height"] == -1


def test_update_actions_fit_narrow_scaled_dialog(viewport):
    open_dialog("update.modal", DisplayScale(2))
    buttons = dpg.get_item_children("update.modal.actions", 1)
    widths = [dpg.get_item_configuration(button)["width"] for button in buttons]
    assert sum(widths) + 16 <= 528


def test_release_notes_wrap_inside_bordered_child(viewport):
    open_dialog("update.modal", DisplayScale())
    body_items = dpg.get_item_children("update.modal.body", 1)
    notes_window = next(
        item for item in body_items
        if dpg.get_item_info(item)["type"] == "mvAppItemType::mvChildWindow"
    )
    notes = dpg.get_item_children(notes_window, 1)[0]
    assert 0 < dpg.get_item_configuration(notes)["wrap"] <= 362


@pytest.mark.skipif(
    os.environ.get("SPECTREXCEL_GUI_TESTS") != "1",
    reason="Opt-in rendered checks require a desktop display",
)
@pytest.mark.parametrize("factor", [1, 2])
def test_rendered_dialog_content_and_actions_fit_after_resize(tmp_path, factor):
    # Dear PyGui's renderer must run in a fresh process, separate from headless
    # context tests and from previous renderer lifecycles.
    subprocess.run(
        [sys.executable, "-c",
         "import runpy, sys; from pathlib import Path; "
         "runpy.run_path(sys.argv[1])['_check_rendered_dialogs'](int(sys.argv[2]), Path(sys.argv[3]))",
         __file__, str(factor), str(tmp_path)],
        check=True, timeout=60,
    )


def _check_rendered_dialogs(factor, tmp_path):
    settings_module.user_config_path = lambda *_args: tmp_path
    scale = DisplayScale(factor)
    dpg.create_context()
    dpg.create_viewport(width=800 * factor, height=560 * factor)
    app = SpectrExcelApp("test", scale)
    app.submit = lambda *_args: None
    try:
        app.build()
        dpg.setup_dearpygui()
        dpg.show_viewport()
        from spectrexcel.dialogs import maintain_dialogs

        for kind in DIALOGS:
            open_dialog(kind, scale, long_content=True)
            for width, height in ((800, 560), (720, 520)):
                dpg.configure_viewport(0, width=width * factor, height=height * factor)
                for frame in range(8):
                    maintain_dialogs()
                    dpg.render_dearpygui_frame()
                viewport_width = dpg.get_viewport_client_width()
                viewport_height = dpg.get_viewport_client_height()
                x, y = dpg.get_item_pos(kind)
                dialog_width, dialog_height = dpg.get_item_rect_size(kind)
                assert 0 <= x <= viewport_width - dialog_width
                assert 0 <= y <= viewport_height - dialog_height
                assert dpg.get_y_scroll_max(kind) == 0
                for button in dpg.get_item_children(f"{kind}.actions", 1):
                    state = dpg.get_item_state(button)
                    assert state["visible"]
                    assert state["rect_max"][0] <= x + dialog_width
                    assert state["rect_max"][1] <= y + dialog_height
                if kind in ("kinetics.reorder.modal", "update.modal"):
                    body = dpg.get_item_children(f"{kind}.body", 1)
                    nested = next(
                        item for item in body
                        if dpg.get_item_info(item)["type"] == "mvAppItemType::mvChildWindow"
                    )
                    if kind == "kinetics.reorder.modal":
                        text = dpg.get_alias_id("kinetics.reorder.filename.0")
                    else:
                        text = dpg.get_item_children(nested, 1)[0]
                    right = (
                        x + dpg.get_item_pos(f"{kind}.body")[0]
                        + dpg.get_item_pos(nested)[0] + dpg.get_item_rect_size(nested)[0]
                    )
                    assert dpg.get_item_state(text)["rect_max"][0] <= right - scale.pixels(18)
            dpg.delete_item(kind)
            dpg.render_dearpygui_frame()
    finally:
        app.shutdown()
        dpg.destroy_context()
