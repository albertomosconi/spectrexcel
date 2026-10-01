import dearpygui.dearpygui as dpg
import pytest

from spectrexcel.assays.view import AssayView, ChartSeries, ChartSpec
from spectrexcel.dpi import DisplayScale


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
    view = AssayView(lambda message: None, lambda *args: None, None, DisplayScale())
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

    plot = dpg.get_item_children("chart.preview.modal.body", 1)[0]
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
    view = AssayView(lambda message: None, lambda *args: None, None, DisplayScale())
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
