from pathlib import Path

import dearpygui.dearpygui as dpg
import pandas as pd
import pytest

from spectrexcel.assays.cinetiche import Cinetiche
from spectrexcel.assays.famiglia_di_spettri import FamigliaDiSpettri
from spectrexcel.assays.titolazione import BindingTitolazione
from spectrexcel.dpi import DisplayScale
from spectrexcel.i18n import get_language, set_language
from spectrexcel.layouts import PARAMETERS_ONLY, PARAMETERS_PREVIEW
from spectrexcel.settings import Settings


@pytest.fixture
def live_context(monkeypatch, tmp_path):
    language = get_language()
    set_language("en")
    monkeypatch.setattr("spectrexcel.settings.user_config_path", lambda *args: tmp_path)
    dpg.create_context()
    dpg.create_viewport(width=1000, height=800)
    dpg.add_theme(tag="theme.accent")
    dpg.add_theme(tag="theme.muted")
    monkeypatch.setattr(dpg, "get_viewport_client_width", lambda: 1000)
    monkeypatch.setattr(dpg, "get_viewport_client_height", lambda: 800)
    views = []

    def create(cls=BindingTitolazione, data=True, layout=PARAMETERS_PREVIEW):
        jobs, messages = [], []
        view = cls(messages.append, lambda *job: jobs.append(job), Settings(), DisplayScale())
        view.mount(dpg.add_window(), layout)
        if data:
            if cls is BindingTitolazione:
                view.dataframe = pd.DataFrame({"#Sample": ["first"], 300: [1.0], 800: [0.25]})
            else:
                frame = pd.DataFrame({0: [1.0, 0.25], 10: [0.5, 0.25]}, index=[300, 800])
                if cls is Cinetiche:
                    view.datasets = [("first", frame), ("second", frame)]
                else:
                    view.dataframe = frame
            view.input_path = Path("input.KD")
        views.append(view)
        return view, jobs, messages

    try:
        yield create
    finally:
        for view in views:
            view.dispose()
        dpg.destroy_context()
        set_language(language)


def complete(job):
    task, success, failure = job
    try:
        result = task()
    except Exception as error:
        failure(error)
    else:
        success(result)


def traces(view):
    plot = view._embedded_renderer.plot
    if plot is None:
        return []
    axes = [item for item in dpg.get_item_children(plot, 1)
            if dpg.get_item_info(item)["type"] == "mvAppItemType::mvPlotAxis"]
    return [dpg.get_value(item)[:2] for item in dpg.get_item_children(axes[1], 1)]


@pytest.mark.parametrize("cls", [BindingTitolazione, Cinetiche, FamigliaDiSpettri])
def test_load_completion_automatically_renders_current_parameters(live_context, cls):
    view, jobs, messages = live_context(cls)
    view.submit_load(lambda: None, lambda result: None, loading_text="Loading", failure_text="Failed")
    assert "Loading" in dpg.get_value(view._preview_message)
    view.process_preview()
    assert len(jobs) == 1  # only input load, not a chart for stale data
    complete(jobs[0])
    view.process_preview()
    assert len(jobs) == 2
    complete(jobs[1])
    assert traces(view)
    assert not dpg.get_item_configuration(view._preview_message)["show"]


@pytest.mark.parametrize("cls", [BindingTitolazione, Cinetiche, FamigliaDiSpettri])
def test_empty_preview_guides_user_without_submitting_work(live_context, cls):
    view, jobs, messages = live_context(cls, data=False)
    view.process_preview()
    assert jobs == []
    assert "Select input files" in dpg.get_value(view._preview_message)
    assert traces(view) == []


def test_parameter_updates_coalesce_and_reject_old_result(live_context, monkeypatch):
    view, jobs, messages = live_context()
    view.request_preview()
    view.process_preview()
    assert len(jobs) == 1
    for value in (400, 500, 600):
        dpg.set_value("binding.x_max", value)
        dpg.get_item_callback("binding.x_max")("binding.x_max", value)
        view.process_preview()
    assert len(jobs) == 1
    complete(jobs[0])
    assert traces(view) == []
    view.process_preview()
    assert len(jobs) == 2
    limits = []
    monkeypatch.setattr(dpg, "set_axis_limits", lambda axis, lo, hi: limits.append((lo, hi)))
    complete(jobs[1])
    assert limits[0] == (200.0, 600.0)
    assert len(traces(view)) == 1


@pytest.mark.parametrize("cls,tag,value", [
    (BindingTitolazione, "binding.x_min", 220),
    (BindingTitolazione, "binding.x_max", 850),
    (BindingTitolazione, "binding.y_min", -0.5),
    (BindingTitolazione, "binding.y_max", 1.5),
    (BindingTitolazione, "binding.correction_enabled", True),
    (BindingTitolazione, "binding.correction", 300),
    (Cinetiche, "kinetics.reading", 800),
    (Cinetiche, "kinetics.correction", 300),
    (FamigliaDiSpettri, "spectra.correction_enabled", True),
    (FamigliaDiSpettri, "spectra.correction", 300),
])
def test_chart_control_callbacks_refresh_preview(live_context, cls, tag, value):
    view, jobs, messages = live_context(cls)
    view.request_preview()
    view.process_preview()
    complete(jobs.pop())
    assert traces(view)
    dpg.set_value(tag, value)
    callback = dpg.get_item_callback(tag)
    assert callback is not None
    callback(tag, value)
    assert traces(view) == []
    view.process_preview()
    complete(jobs.pop())
    assert traces(view)
    if tag.endswith("correction_enabled"):
        correction = tag.replace("_enabled", "")
        assert dpg.get_item_configuration(correction)["show"]
        assert traces(view)[0][1] == [0.75, 0.0]


def test_info_option_does_not_recompute_chart(live_context):
    view, jobs, messages = live_context()
    view.request_preview()
    view.process_preview()
    complete(jobs.pop())
    dpg.set_value("binding.info", True)
    dpg.get_item_callback("binding.info")("binding.info", True)
    view.process_preview()
    assert jobs == []
    assert traces(view)


@pytest.mark.parametrize("cls,tag", [(BindingTitolazione, "binding.correction"),
                                    (Cinetiche, "kinetics.reading"),
                                    (FamigliaDiSpettri, "spectra.correction")])
def test_invalid_wavelength_clears_chart_and_recovers_without_log_spam(live_context, cls, tag):
    view, jobs, messages = live_context(cls)
    if cls is not Cinetiche:
        dpg.set_value(tag + "_enabled", True)
    view.request_preview()
    view.process_preview()
    complete(jobs.pop())
    dpg.set_value(tag, 801)
    dpg.get_item_callback(tag)(tag, 801)
    view.process_preview()
    complete(jobs.pop())
    assert traces(view) == []
    assert "801" in dpg.get_value(view._preview_message)
    assert messages == []
    dpg.set_value(tag, 300)
    dpg.get_item_callback(tag)(tag, 300)
    view.process_preview()
    complete(jobs.pop())
    assert traces(view)


def test_invalid_axis_range_clears_chart_and_recovers(live_context):
    view, jobs, messages = live_context()
    view.request_preview()
    view.process_preview()
    complete(jobs.pop())
    for maximum in (100, 900):
        dpg.set_value("binding.x_max", maximum)
        dpg.get_item_callback("binding.x_max")("binding.x_max", maximum)
        view.process_preview()
        complete(jobs.pop())
        assert bool(traces(view)) == (maximum == 900)


@pytest.mark.parametrize("cls", [BindingTitolazione, Cinetiche, FamigliaDiSpettri])
def test_failed_replacement_load_stays_error_until_success(live_context, cls):
    view, jobs, messages = live_context(cls)
    view.request_preview()
    view.process_preview()
    complete(jobs.pop())
    view.submit_load(lambda: None, lambda result: None, loading_text="Loading", failure_text="Failed")
    jobs.pop()[2](ValueError("bad input"))
    for layout in (PARAMETERS_ONLY, PARAMETERS_PREVIEW):
        view.apply_layout(layout)
        view.request_preview()
        view.process_preview()
    assert jobs == []
    assert traces(view) == []
    assert "failed" in dpg.get_value(view._preview_message)
    view.submit_load(lambda: None, lambda result: None, loading_text="Loading", failure_text="Failed")
    complete(jobs.pop())
    view.process_preview()
    complete(jobs.pop())
    assert traces(view)


def test_layout_switch_invalidates_pending_results(live_context):
    view, jobs, messages = live_context()
    view.request_preview()
    view.process_preview()
    view.apply_layout(PARAMETERS_ONLY)
    dpg.set_value("binding.correction_enabled", True)
    view.apply_layout(PARAMETERS_PREVIEW)
    complete(jobs.pop())
    assert traces(view) == []
    view.process_preview()
    complete(jobs.pop())
    assert traces(view)[0][1] == [0.75, 0.0]


def test_reorder_updates_legend_and_trace_order(live_context):
    view, jobs, messages = live_context(Cinetiche)
    view.request_preview()
    view.process_preview()
    complete(jobs.pop())
    view._show_reorder()
    view._move_dataset(None, None, (0, 1))
    view.process_preview()
    complete(jobs.pop())
    plot = view._embedded_renderer.plot
    axis = dpg.get_item_children(plot, 1)[-1]
    assert [dpg.get_item_label(item) for item in dpg.get_item_children(axis, 1)] == ["second", "first"]


def test_disposed_view_suppresses_preview_results(live_context):
    view, jobs, messages = live_context()
    view.request_preview()
    view.process_preview()
    view.dispose()
    complete(jobs.pop())
    assert traces(view) == []


def test_export_completion_survives_layout_switch(live_context):
    view, jobs, messages = live_context()
    view.submit_export(lambda: None)
    view.apply_layout(PARAMETERS_ONLY)
    assert not dpg.get_item_configuration("binding.preview")["enabled"]
    complete(jobs.pop())
    assert dpg.get_item_configuration("binding.preview")["enabled"]
    assert messages[-1] == "excel file saved successfully"


def test_worker_calculation_does_not_read_widgets(live_context, monkeypatch):
    view, jobs, messages = live_context()
    view.request_preview()
    view.process_preview()
    monkeypatch.setattr(dpg, "get_value", lambda tag: pytest.fail("worker read a widget"))
    complete(jobs.pop())
    assert view._embedded_renderer.plot is not None


def test_default_layout_never_automatically_opens_preview(live_context):
    view, jobs, messages = live_context(layout=PARAMETERS_ONLY)
    view.request_preview()
    view.process_preview()
    assert jobs == []
    assert not dpg.does_item_exist("chart.preview.modal")


def test_refresh_replaces_resources_without_accumulating_items(live_context):
    view, jobs, messages = live_context()
    sizes = []
    for _iteration in range(6):
        view.request_preview()
        view.process_preview()
        complete(jobs.pop())
        sizes.append(len(dpg.get_all_items()))
    assert len(set(sizes)) == 1


def test_parameter_changes_during_load_use_latest_values(live_context):
    view, jobs, messages = live_context()
    view.submit_load(lambda: None, lambda result: None, loading_text="Loading", failure_text="Failed")
    dpg.set_value("binding.correction_enabled", True)
    dpg.get_item_callback("binding.correction_enabled")("binding.correction_enabled", True)
    view.process_preview()
    assert len(jobs) == 1
    complete(jobs.pop())
    view.process_preview()
    complete(jobs.pop())
    assert traces(view)[0][1] == [0.75, 0.0]


def test_worker_failure_does_not_block_newer_refresh(live_context):
    view, jobs, messages = live_context()
    view.request_preview()
    view.process_preview()
    view.request_preview()
    jobs.pop()[2](RuntimeError("obsolete failure"))
    assert "obsolete failure" not in dpg.get_value(view._preview_message)
    view.process_preview()
    complete(jobs.pop())
    assert traces(view)
