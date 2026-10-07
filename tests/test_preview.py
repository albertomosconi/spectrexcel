import dearpygui.dearpygui as dpg
import os
import pytest
import subprocess
import sys
import pandas as pd
from pathlib import Path
from unittest.mock import Mock

from spectrexcel.assays.view import AssayView, CHROME_HEADER_THEME, CHROME_TAB_THEME, ChartSeries, ChartSpec
from spectrexcel.dpi import DisplayScale
from spectrexcel.settings import Settings


def test_binding_chart_builder_corrects_without_mutating():
    from spectrexcel.assays.titolazione import binding_chart_spec
    frame = pd.DataFrame({"#Sample": ["one"], "Std.Dev.": [0.1],
                          "300": [1.0], "800": [0.25]})
    original = frame.copy(deep=True)
    spec = binding_chart_spec(frame, 200, 900, -1.0, 2.0, 800)
    assert spec.series[0].x == [300.0, 800.0]
    assert spec.series[0].y == [0.75, 0.0]
    assert spec.x_limits == (200.0, 900.0)
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("bounds,correction", [((900, 200, 0.0, 1.0), None),
                                                 ((200, 900, 1.0, 0.0), None),
                                                 ((200, 900, 0.0, 1.0), 801)])
def test_binding_chart_builder_rejects_invalid_parameters(bounds, correction):
    from spectrexcel.assays.titolazione import binding_chart_spec
    frame = pd.DataFrame({"#Sample": ["one"], 300: [1.0], 800: [0.25]})
    with pytest.raises(ValueError):
        x_min, x_max, y_min, y_max = bounds
        binding_chart_spec(frame, x_min, x_max, y_min, y_max, correction)


def test_family_chart_builder_preserves_stride_title_and_negative_limits():
    from spectrexcel.assays.famiglia_di_spettri import spectrum_family_chart_spec
    frame = pd.DataFrame({0: [1.0, 0.25], 10: [0.5, 0.5], 20: [0.25, 0.5]},
                         index=[300, 800])
    original = frame.copy(deep=True)
    spec = spectrum_family_chart_spec(frame, Path("experiment.KD"), 800)
    assert spec.title == "experiment"
    assert [s.name for s in spec.series] == ["0", "20"]
    assert [s.y for s in spec.series] == [[0.75, 0.0], [-0.25, 0.0]]
    assert spec.y_limits == (-0.25, 0.75)
    assert spec.x_limits == (190.0, 1100.0)
    pd.testing.assert_frame_equal(frame, original)
    with pytest.raises(ValueError, match="801"):
        spectrum_family_chart_spec(frame, Path("experiment.KD"), 801)


def test_kinetics_preview_task_snapshots_parameters_and_order(monkeypatch):
    from spectrexcel.assays.cinetiche import Cinetiche
    view = Cinetiche(lambda message: None, lambda *args: None, None, DisplayScale())
    frame = pd.DataFrame({0: [1.0, 0.25], 10: [0.5, 0.25]}, index=[300, 800])
    view.datasets = [("first", frame), ("second", frame)]
    values = {"kinetics.reading": 300, "kinetics.correction": 800}
    monkeypatch.setattr(dpg, "get_value", values.__getitem__)
    task = view.preview_task()
    assert task is not None
    view.datasets.reverse()
    values["kinetics.reading"] = 801
    monkeypatch.setattr(dpg, "get_value", lambda tag: pytest.fail("worker read widget"))
    spec = task()
    assert [s.name for s in spec.series] == ["first", "second"]
    assert spec.series[0].y == [0.75, 0.25]


@pytest.fixture
def preview_context(monkeypatch):
    dpg.create_context()
    dpg.create_viewport(width=1000, height=800)
    monkeypatch.setattr(dpg, "get_viewport_client_width", lambda: 1000)
    monkeypatch.setattr(dpg, "get_viewport_client_height", lambda: 800)
    try:
        yield
    finally:
        dpg.destroy_context()


@pytest.mark.parametrize("legend", [False, True])
def test_chart_preview_emits_series_coordinates_labels_and_axis_limits(preview_context, monkeypatch, legend):
    view = AssayView(lambda message: None, lambda *args: None, Mock(spec=Settings), DisplayScale())
    limits = {}
    set_axis_limits = dpg.set_axis_limits

    def capture_limits(axis, minimum, maximum):
        # Headless contexts expose series values, but axis limits are only
        # readable after rendering. Inspect the real renderer API boundary.
        limits[dpg.get_item_label(axis)] = (minimum, maximum)
        set_axis_limits(axis, minimum, maximum)

    monkeypatch.setattr(dpg, "set_axis_limits", capture_limits)
    spec = ChartSpec(
        "Time (s)", "Abs (AU)", (0.0, 10.0), (-0.5, 1.0),
        (ChartSeries("first", [0.0, 10.0], [-0.25, 0.75]),
         ChartSeries("second", [0.0, 10.0], [0.5, 0.25])),
        title="Two traces", legend=legend,
    )

    view.show_chart_preview(spec)

    plot = next(item for item in dpg.get_item_children("chart.preview.modal.body", 1)
                if dpg.get_item_info(item)["type"] == "mvAppItemType::mvPlot")
    assert dpg.get_item_label(plot) == "Two traces"
    items = dpg.get_item_children(plot, 1)
    axes = [item for item in items if dpg.get_item_info(item)["type"] == "mvAppItemType::mvPlotAxis"]
    assert [dpg.get_item_label(axis) for axis in axes] == ["Time (s)", "Abs (AU)"]
    assert limits == {"Time (s)": (0.0, 10.0), "Abs (AU)": (-0.5, 1.0)}
    series = dpg.get_item_children(axes[1], 1)
    assert len(series) == 2
    assert dpg.get_value(series[0])[:2] == [[0.0, 10.0], [-0.25, 0.75]]
    assert dpg.get_value(series[1])[:2] == [[0.0, 10.0], [0.5, 0.25]]
    assert [dpg.get_item_label(item) for item in series] == (
        ["first", "second"] if legend else ["##series0", "##series1"]
    )
    legends = [item for item in dpg.get_item_children(plot, 0)
               if dpg.get_item_info(item)["type"] == "mvAppItemType::mvPlotLegend"]
    assert len(legends) == int(legend)


def test_reopening_chart_preview_replaces_old_series(preview_context):
    view = AssayView(lambda message: None, lambda *args: None, Mock(spec=Settings), DisplayScale())
    view.show_chart_preview(ChartSpec("x", "y", (0, 1), (0, 1), (
        ChartSeries("old", [0, 1], [0.2, 0.3]),
    )))

    view.show_chart_preview(ChartSpec("x", "y", (0, 1), (0, 1), (
        ChartSeries("new", [0, 1], [0.8, 0.9]),
    )))

    series = [item for item in dpg.get_all_items()
              if dpg.get_item_info(item)["type"] == "mvAppItemType::mvLineSeries"]
    assert len(series) == 1
    assert dpg.get_value(series[0])[:2] == [[0.0, 1.0], [0.8, 0.9]]


def test_renderer_expands_equal_bounds_only_for_display(preview_context, monkeypatch):
    from spectrexcel.charts import ChartRenderer
    parent = dpg.add_window()
    calls = []
    monkeypatch.setattr(dpg, "set_axis_limits",
                        lambda axis, lo, hi: calls.append((lo, hi)))
    spec = ChartSpec("x", "y", (0, 0), (0, 0),
                     (ChartSeries("one", [0], [0]),))
    renderer = ChartRenderer(parent, DisplayScale())
    renderer.render(spec)
    assert calls == [(0, 1.0), (0, 1.0)]
    assert spec.x_limits == spec.y_limits == (0, 0)
    renderer.dispose()


def test_renderer_unlocks_pan_zoom_after_first_rendered_frame(preview_context, monkeypatch):
    from spectrexcel.charts import ChartRenderer
    parent = dpg.add_window()
    unlocked = []
    frames = {"count": 0}
    monkeypatch.setattr(dpg, "get_frame_count", lambda: frames["count"])
    monkeypatch.setattr(dpg, "set_axis_limits_auto", unlocked.append)
    spec = ChartSpec(
        "x", "y", (0, 10), (-1, 2),
        (ChartSeries("one", [0, 10], [-0.25, 0.75]),),
    )
    renderer = ChartRenderer(parent, DisplayScale())
    renderer.render(spec)
    renderer.maintain()
    # Dear PyGui locks pan/zoom while set_axis_limits is in effect, so
    # renderer.maintain must wait for the limits to be applied once.
    assert unlocked == []
    frames["count"] = 1
    renderer.maintain()
    assert unlocked == renderer.axes
    renderer.maintain()
    assert len(unlocked) == 2


def test_assay_view_unlocks_modal_chart_zoom(preview_context, monkeypatch):
    view = AssayView(lambda message: None, lambda *args: None, Mock(spec=Settings), DisplayScale())
    view.show_chart_preview(ChartSpec("x", "y", (0, 1), (0, 1), (
        ChartSeries("one", [0, 1], [0.2, 0.3]),
    )))
    unlocked = []
    frames = {"count": 0}
    monkeypatch.setattr(dpg, "get_frame_count", lambda: frames["count"])
    monkeypatch.setattr(dpg, "set_axis_limits_auto", unlocked.append)

    view.maintain_charts()
    frames["count"] = 1
    view.maintain_charts()

    assert unlocked == view._modal_renderer.axes  # pyright: ignore[reportOptionalMemberAccess]


def test_renderer_builds_zoom_toolbar_above_chart(preview_context):
    from spectrexcel.charts import ChartRenderer
    parent = dpg.add_window()
    renderer = ChartRenderer(parent, DisplayScale())
    spec = ChartSpec(
        "x", "y", (0, 10), (-1, 2),
        (ChartSeries("one", [0, 10], [-0.25, 0.75]),),
    )
    renderer.render(spec)
    rendered = dpg.get_item_children(parent, 1)
    toolbar = next(item for item in rendered
                   if dpg.get_item_info(item)["type"] == "mvAppItemType::mvGroup")
    children = dpg.get_item_children(toolbar, 1)
    buttons = [item for item in children
               if dpg.get_item_info(item)["type"] == "mvAppItemType::mvButton"]
    assert [dpg.get_item_label(item) for item in buttons] == ["\u21ba"]
    for button in buttons:
        config = dpg.get_item_configuration(button)
        assert config["width"] == config["height"] == DisplayScale().pixels(32)
    nested = [item for item in children
              if dpg.is_item_container(item)
              and dpg.get_item_info(item)["type"] != "mvAppItemType::mvTooltip"]
    texts = [dpg.get_value(item) for group in nested
             for item in dpg.get_item_children(group, 1)
             if dpg.get_item_info(item)["type"] == "mvAppItemType::mvText"]
    assert texts == ["Click and drag to pan. Scroll to zoom."]


def test_renderer_reset_button_disabled_until_view_drifts(preview_context, monkeypatch):
    from spectrexcel.charts import ChartRenderer
    parent = dpg.add_window()
    current = {"x": (0.0, 10.0), "y": (-1.0, 2.0)}
    frames = {"count": 0}
    monkeypatch.setattr(dpg, "get_frame_count", lambda: frames["count"])
    monkeypatch.setattr(
        dpg, "get_axis_limits",
        lambda axis: dict(zip(renderer.axes, (current["x"], current["y"])))[axis],
    )
    spec = ChartSpec(
        "x", "y", (0, 10), (-1, 2),
        (ChartSeries("one", [0, 10], [-0.25, 0.75]),),
    )
    renderer = ChartRenderer(parent, DisplayScale())
    renderer.render(spec)
    reset = renderer.toolbar_buttons[0]
    assert not dpg.get_item_configuration(reset)["enabled"]

    frames["count"] += 1
    renderer.maintain()  # unlock; view equals spec limits
    assert not dpg.get_item_configuration(reset)["enabled"]

    renderer.reset_view()
    frames["count"] += 1
    renderer.maintain()  # queued command: view has moved
    assert dpg.get_item_configuration(reset)["enabled"]

    frames["count"] += 1
    renderer.maintain()  # apply phase
    frames["count"] += 1
    renderer.maintain()  # release phase
    frames["count"] += 1
    renderer.maintain()  # back at spec limits
    assert not dpg.get_item_configuration(reset)["enabled"]


def test_renderer_reset_enables_and_disables_with_rendered_limits(
    preview_context, monkeypatch
):
    from spectrexcel.charts import ChartRenderer
    parent = dpg.add_window()
    current = {"x": (0.0, 10.0), "y": (-1.0, 2.0)}
    frames = {"count": 0}
    monkeypatch.setattr(dpg, "get_frame_count", lambda: frames["count"])
    monkeypatch.setattr(
        dpg, "get_axis_limits",
        lambda axis: dict(zip(renderer.axes, (current["x"], current["y"])))[axis],
    )
    spec = ChartSpec(
        "x", "y", (0, 10), (-1, 2),
        (ChartSeries("one", [0, 10], [-0.25, 0.75]),),
    )
    renderer = ChartRenderer(parent, DisplayScale())
    renderer.render(spec)
    reset = renderer.toolbar_buttons[0]
    renderer.interactive = True

    renderer.maintain()  # view at spec limits: disabled
    assert not dpg.get_item_configuration(reset)["enabled"]
    current["x"] = (2.0, 8.0)
    frames["count"] += 1
    renderer.maintain()  # drifted: enabled
    assert dpg.get_item_configuration(reset)["enabled"]
    current["x"] = (0.0, 10.0)
    frames["count"] += 1
    renderer.maintain()  # back at spec limits: disabled again
    assert not dpg.get_item_configuration(reset)["enabled"]


def test_renderer_reset_view_restores_spec_limits(preview_context, monkeypatch):
    from spectrexcel.charts import ChartRenderer
    parent = dpg.add_window()
    applied = []
    released = []
    frames = {"count": 0}
    monkeypatch.setattr(dpg, "get_frame_count", lambda: frames["count"])
    spec = ChartSpec(
        "x", "y", (0, 10), (-1, 2),
        (ChartSeries("one", [0, 10], [-0.25, 0.75]),),
    )
    renderer = ChartRenderer(parent, DisplayScale())
    renderer.render(spec)
    monkeypatch.setattr(dpg, "set_axis_limits", lambda axis, lo, hi: applied.append((lo, hi)))
    monkeypatch.setattr(dpg, "set_axis_limits_auto", lambda axis: released.append(axis))
    frames["count"] = 1
    renderer.maintain()  # unlock; interactive now

    renderer.reset_view()
    frames["count"] = 2
    renderer.maintain()  # apply phase
    assert applied == [(0, 10), (-1, 2)]
    frames["count"] = 3
    renderer.maintain()  # release phase
    assert released[2:] == renderer.axes


def test_renderer_reset_tolerates_float32_limit_rounding(preview_context, monkeypatch):
    """Dear PyGui truncates limits to single precision; that is not a drift."""
    from spectrexcel.charts import ChartRenderer
    parent = dpg.add_window()
    current = {"x": (0.0, 298.70001220703125), "y": (0.0, 1.1445660591125488)}
    frames = {"count": 0}
    monkeypatch.setattr(dpg, "get_frame_count", lambda: frames["count"])
    monkeypatch.setattr(
        dpg, "get_axis_limits",
        lambda axis: dict(zip(renderer.axes, (current["x"], current["y"])))[axis],
    )
    spec = ChartSpec(
        "x", "y", (0.0, 298.7), (0.0, 1.1445660591125488),
        (ChartSeries("one", [0, 298.7], [0.2, 0.3]),),
    )
    renderer = ChartRenderer(parent, DisplayScale())
    renderer.render(spec)
    reset = renderer.toolbar_buttons[0]
    renderer.interactive = True

    renderer.maintain()  # float32-rounded readback of the spec: not drifted
    assert not dpg.get_item_configuration(reset)["enabled"]


@pytest.mark.skipif(
    os.environ.get("SPECTREXCEL_GUI_TESTS") != "1",
    reason="Opt-in rendered checks require a desktop display",
)
@pytest.mark.parametrize("factor", [1, 2])
def test_rendered_chart_toolbar_centers_hint(factor):
    # Dear PyGui's renderer must run in a fresh process, separate from headless
    # context tests and from previous renderer lifecycles.
    subprocess.run(
        [sys.executable, "-c",
         "import runpy, sys; "
         "runpy.run_path(sys.argv[1])['_check_rendered_chart_toolbar'](int(sys.argv[2]))",
         __file__, str(factor)],
        check=True, timeout=60,
    )


def _check_rendered_chart_toolbar(factor):
    dpg.create_context()
    dpg.create_viewport(width=1280 * factor, height=800 * factor)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    try:
        from spectrexcel.charts import ChartRenderer
        window = dpg.add_window()
        spec = ChartSpec(
            "Time (s)", "Abs (AU)", (0.0, 10.0), (-0.5, 1.0),
            (ChartSeries("first", [0.0, 10.0], [-0.25, 0.75]),),
        )
        renderer = ChartRenderer(window, DisplayScale(factor))
        renderer.render(spec)
        for _frame in range(6):
            renderer.maintain()
            dpg.render_dearpygui_frame()
        button = dpg.get_item_state(renderer.toolbar_buttons[0])
        assert renderer.hint_text is not None
        hint = dpg.get_item_state(renderer.hint_text)
        button_center = button["pos"][1] + button["rect_size"][1] / 2
        hint_center = hint["pos"][1] + hint["rect_size"][1] / 2
        assert hint_center == pytest.approx(button_center, abs=1)
        # The reset button starts disabled at the initial view.
        assert not dpg.get_item_configuration(renderer.toolbar_buttons[0])["enabled"]
    finally:
        dpg.destroy_context()


def test_renderer_replaces_and_disposes_owned_themes(preview_context):
    from spectrexcel.charts import ChartRenderer
    parent = dpg.add_window()
    before = set(dpg.get_all_items())
    renderer = ChartRenderer(parent, DisplayScale())
    spec = ChartSpec("x", "y", (0, 1), (0, 1),
                     (ChartSeries("one", [0, 1], [0.2, 0.3]),))
    sizes = []
    for _iteration in range(5):
        renderer.render(spec)
        sizes.append(len(dpg.get_all_items()))
    assert len(set(sizes)) == 1
    renderer.clear()
    assert set(dpg.get_all_items()) == before
    renderer.render(spec)
    dpg.delete_item(parent)
    renderer.dispose()
    assert not [item for item in dpg.get_all_items()
                if dpg.get_item_info(item)["type"] == "mvAppItemType::mvTheme"]


def test_assay_dispose_closes_modal_and_shares_chrome_themes(preview_context):
    view = AssayView(lambda message: None, lambda *args: None, Mock(spec=Settings), DisplayScale())
    before = set(dpg.get_all_items())
    view.show_chart_preview(ChartSpec("x", "y", (0, 1), (0, 1),
                           (ChartSeries("one", [0, 1], [0.2, 0.3]),)))
    chrome = set()
    for theme in (CHROME_HEADER_THEME, CHROME_TAB_THEME):
        chrome.add(dpg.get_alias_id(theme))
        for slot in range(3):
            chrome.update(dpg.get_item_children(theme, slot) or [])
        for component in dpg.get_item_children(theme, 1) or []:
            for sub_slot in range(3):
                chrome.update(dpg.get_item_children(component, sub_slot) or [])
    view.dispose()
    # The dialog and everything the view owns goes away; the chrome tab themes
    # are context-shared assets other views may still need.
    assert set(dpg.get_all_items()) - chrome == before
