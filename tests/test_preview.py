import dearpygui.dearpygui as dpg
import pytest
import pandas as pd
from pathlib import Path

from spectrexcel.assays.view import AssayView, ChartSeries, ChartSpec
from spectrexcel.dpi import DisplayScale


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
        binding_chart_spec(frame, *bounds, correction)


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


def test_renderer_expands_equal_bounds_only_for_display(preview_context, monkeypatch):
    from spectrexcel.charts import ChartRenderer
    parent = dpg.add_window()
    calls = []
    monkeypatch.setattr(dpg, "set_axis_limits",
                        lambda axis, lo, hi: calls.append((lo, hi)))
    spec = ChartSpec("x", "y", (0, 0), (0, 0),
                     (ChartSeries("one", [0], [0]),))
    renderer = ChartRenderer(parent)
    renderer.render(spec)
    assert calls == [(0, 1.0), (0, 1.0)]
    assert spec.x_limits == spec.y_limits == (0, 0)
    renderer.dispose()


def test_renderer_replaces_and_disposes_owned_themes(preview_context):
    from spectrexcel.charts import ChartRenderer
    parent = dpg.add_window()
    before = set(dpg.get_all_items())
    renderer = ChartRenderer(parent)
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


def test_assay_dispose_closes_modal_and_owned_themes(preview_context):
    view = AssayView(lambda message: None, lambda *args: None, None, DisplayScale())
    before = set(dpg.get_all_items())
    view.show_chart_preview(ChartSpec("x", "y", (0, 1), (0, 1),
                           (ChartSeries("one", [0, 1], [0.2, 0.3]),)))
    view.dispose()
    assert set(dpg.get_all_items()) == before
