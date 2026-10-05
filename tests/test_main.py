import dearpygui.dearpygui as dpg
import pytest
import requests
import pandas as pd
from pathlib import Path
from threading import Event, get_ident

import spectrexcel.main as main_module
from spectrexcel.dpi import DisplayScale
from spectrexcel.i18n import TRANSLATIONS_IT
from spectrexcel.i18n import _, get_language, set_language
from spectrexcel.main import ASSAYS, THEME_COLORS, SpectrExcelApp
from spectrexcel.settings import Settings


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


@pytest.mark.parametrize(
    "language, fallback_tooltip, version_tooltip",
    [
        ("en", "All versions; resolves to latest release.", "Cite SpectrExcel version 1.7.0."),
        ("it", "Tutte le versioni; rimanda alla versione più recente.", "Cita SpectrExcel versione 1.7.0."),
    ],
)
def test_footer_uses_concept_doi_until_exact_version_resolves(
    dpg_context, monkeypatch, tmp_path, language, fallback_tooltip, version_tooltip
):
    monkeypatch.setattr("spectrexcel.settings.user_config_path", lambda *_args: tmp_path)
    tasks = []
    monkeypatch.setattr(SpectrExcelApp, "submit", lambda self, *args: tasks.append(args))
    opened = []
    monkeypatch.setattr(main_module.webbrowser, "open", opened.append)
    app = SpectrExcelApp("1.7.0", DisplayScale())
    try:
        set_language(language)
        app.build()
        assert dpg.does_item_exist("main.citation")
        assert dpg.get_value("main.citation.prefix") == "DOI: "
        assert dpg.get_item_type("main.citation") == "mvAppItemType::mvText"
        assert dpg.get_value("main.citation") == "10.5281/zenodo.23161786"
        assert dpg.get_value("main.citation.tooltip.text") == fallback_tooltip
        dpg.get_item_callback("main.citation.click")()
        assert opened == ["https://doi.org/10.5281/zenodo.23161786"]
        assert any(task[0] == app._find_citation for task in tasks)

        app._citation_lookup_failed(requests.Timeout("offline"))
        app._citation_lookup_finished(None)
        assert dpg.get_value("main.citation") == "10.5281/zenodo.23161786"

        app._citation_lookup_finished("10.5281/zenodo.23161787")
        assert dpg.get_value("main.citation") == "10.5281/zenodo.23161787"
        assert dpg.get_value("main.citation.tooltip.text") == version_tooltip
        dpg.get_item_callback("main.citation.click")()
        assert opened[-1] == "https://doi.org/10.5281/zenodo.23161787"
    finally:
        app.executor.shutdown(wait=True)


def test_citation_underline_tracks_text_bounds_and_theme(dpg_context, monkeypatch, tmp_path):
    monkeypatch.setattr("spectrexcel.settings.user_config_path", lambda *_args: tmp_path)
    monkeypatch.setattr(SpectrExcelApp, "submit", lambda *_args: None)
    monkeypatch.setattr(dpg, "get_item_rect_min", lambda item: (600, 480))
    monkeypatch.setattr(dpg, "get_item_rect_max", lambda item: (790, 495))
    app = SpectrExcelApp("test", DisplayScale())
    try:
        app.build()
        for theme, color in (("Light", (24, 91, 138)), ("Dark", (104, 190, 255))):
            app.active_theme = theme
            app._draw_citation_underline()
            config = dpg.get_item_configuration("main.citation.underline")
            assert config["p1"][:2] == [600, 495]
            assert config["p2"][:2] == [790, 495]
            assert config["color"][:3] == pytest.approx([channel / 255 for channel in color])
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


@pytest.mark.parametrize(
    "name, expected", [("Light", (30, 34, 40)), ("Dark", (235, 235, 235))]
)
def test_checkbox_labels_use_readable_theme_text(
    dpg_context, monkeypatch, tmp_path, name, expected
):
    monkeypatch.setattr("spectrexcel.settings.user_config_path", lambda *_args: tmp_path)
    monkeypatch.setattr(SpectrExcelApp, "submit", lambda *_args: None)
    app = SpectrExcelApp("test", DisplayScale())
    try:
        app.build()

        components = dpg.get_item_children(f"theme.{name.lower()}", 1)
        checkbox_colors = [
            dpg.get_value(color)[:3]
            for component in components
            if dpg.get_item_configuration(component)["item_type"] == dpg.mvCheckbox
            for color in dpg.get_item_children(component, 1)
            if dpg.get_item_configuration(color)["target"] == dpg.mvThemeCol_Text
        ]
        assert checkbox_colors == [list(expected)]
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


@pytest.fixture
def worker_app(monkeypatch, tmp_path):
    previous_language = get_language()
    monkeypatch.setattr("spectrexcel.settings.user_config_path", lambda *_args: tmp_path)
    app = SpectrExcelApp("test", DisplayScale())
    set_language("en")
    try:
        yield app
    finally:
        app.shutdown()
        set_language(previous_language)


def test_worker_success_waits_for_result_processing_on_calling_thread(worker_app):
    app = worker_app
    started, release = Event(), Event()
    task_threads, callbacks, errors = [], [], []
    processing_thread = get_ident()

    def task():
        task_threads.append(get_ident())
        started.set()
        if not release.wait(timeout=5):
            raise TimeoutError("test did not release worker")
        return "parsed data"

    try:
        app.submit(task, lambda value: callbacks.append((value, get_ident())), errors.append)
        assert started.wait(timeout=5)
        assert app.has_running_tasks()
        app.process_results()
        assert callbacks == []
    finally:
        release.set()
        app.executor.shutdown(wait=True)

    assert not app.has_running_tasks()
    assert callbacks == []
    assert task_threads[0] != processing_thread
    app.process_results()
    assert callbacks == [("parsed data", processing_thread)]
    assert errors == []
    app.process_results()
    assert len(callbacks) == 1


def test_worker_failure_dispatches_original_error_only_when_processed(worker_app):
    app = worker_app
    failure = ValueError("invalid spectrum")
    successes, errors = [], []
    processing_thread = get_ident()

    def task():
        raise failure

    app.submit(task, successes.append, lambda error: errors.append((error, get_ident())))
    app.executor.shutdown(wait=True)

    assert not app.has_running_tasks()
    assert successes == [] and errors == []
    app.process_results()
    assert successes == []
    assert errors == [(failure, processing_thread)]


@pytest.mark.parametrize("task_fails", [False, True])
def test_result_processing_logs_callback_failure_and_continues(worker_app, monkeypatch, task_fails):
    app = worker_app
    messages, received = [], []
    monkeypatch.setattr(app, "log", messages.append)

    def task():
        if task_fails:
            raise ValueError("worker failure")
        return "first"

    def broken_callback(value):
        raise RuntimeError("callback failure")

    app.submit(task, broken_callback, broken_callback)
    app.executor.shutdown(wait=True)
    # Queue the next result after the broken callback, without sleeps.
    app.results.put((received.append, "next result", None))

    app.process_results()

    assert received == ["next result"]
    assert len(messages) == 1 and "callback failure" in messages[0]


@pytest.mark.parametrize("index", range(3))
@pytest.mark.parametrize("language,preview_label,default_label", [
    ("en", "parameters + preview", "parameters only"),
    ("it", "parametri + anteprima", "solo parametri"),
])
def test_layout_setting_preserves_live_assay_state(
    dpg_context, monkeypatch, tmp_path, index, language, preview_label, default_label
):
    monkeypatch.setattr("spectrexcel.settings.user_config_path", lambda *args: tmp_path)
    monkeypatch.setattr(SpectrExcelApp, "submit", lambda *args: None)
    settings = Settings()
    settings.set("main/language", language)
    settings.set("main/selected_assay", index)
    app = SpectrExcelApp("test", DisplayScale())
    try:
        app.build()
        view = app.assay_view
        tag = ("binding.x_min", "kinetics.reading", "spectra.correction")[index]
        dpg.set_value(tag, 333)
        frame = pd.DataFrame({0: [1.0, 0.25], 10: [0.5, 0.25]}, index=[300, 800])
        if index == 1:
            view.datasets = [("second", frame), ("first", frame)]
            data = view.datasets
        else:
            view.dataframe = frame
            view.input_path = Path("original.KD")
            data = view.dataframe
        for label in (preview_label, default_label, preview_label):
            app._layout_changed(None, label)
            assert app.assay_view is view
            assert dpg.get_value(tag) == 333
            assert (view.datasets if index == 1 else view.dataframe) is data
            assert not dpg.get_item_configuration(view.workflow_controls.export)["enabled"]
        assert Settings().get("main/layout", "") == "parameters_preview"
        if index == 1:
            assert [name for name, frame in view.datasets] == ["second", "first"]
        else:
            assert view.input_path == Path("original.KD")
        app._load_assay((index + 1) % 3)
        assert not view.active
        assert app.assay_view.layout == "parameters_preview"
    finally:
        app.shutdown()


@pytest.mark.parametrize("preference,expected", [
    (None, "parameters_only"), ("bad", "parameters_only"),
    ([], "parameters_only"), ("parameters_preview", "parameters_preview"),
])
def test_startup_resolves_saved_layout(dpg_context, monkeypatch, tmp_path, preference, expected):
    monkeypatch.setattr("spectrexcel.settings.user_config_path", lambda *args: tmp_path)
    monkeypatch.setattr(SpectrExcelApp, "submit", lambda *args: None)
    if preference is not None:
        Settings().set("main/layout", preference)
    app = SpectrExcelApp("test", DisplayScale())
    try:
        app.build()
        assert app.layout_preference == expected
        assert app.assay_view.layout == expected
        assert dpg.get_item_configuration("binding.preview")["show"] == (expected == "parameters_only")
    finally:
        app.shutdown()


def test_settings_layout_combo_applies_live(dpg_context, monkeypatch, tmp_path):
    monkeypatch.setattr("spectrexcel.settings.user_config_path", lambda *args: tmp_path)
    monkeypatch.setattr(SpectrExcelApp, "submit", lambda *args: None)
    monkeypatch.setattr(dpg, "get_viewport_client_width", lambda: 800)
    monkeypatch.setattr(dpg, "get_viewport_client_height", lambda: 520)
    Settings().set("main/language", "en")
    app = SpectrExcelApp("test", DisplayScale())
    try:
        app.build()
        app._show_settings()
        assert dpg.get_value("settings.layout") == "parameters only"
        assert dpg.get_item_configuration("settings.layout")["items"] == [
            "parameters only", "parameters + preview"]
        dpg.set_value("settings.layout", "parameters + preview")
        dpg.get_item_callback("settings.layout")("settings.layout", "parameters + preview")
        assert dpg.does_item_exist("settings.modal")
        assert not dpg.get_item_configuration("binding.preview")["show"]
    finally:
        app.shutdown()


def test_layout_save_failure_logs_but_applies_and_unknown_label_ignored(dpg_context, monkeypatch, tmp_path):
    monkeypatch.setattr("spectrexcel.settings.user_config_path", lambda *args: tmp_path)
    monkeypatch.setattr(SpectrExcelApp, "submit", lambda *args: None)
    Settings().set("main/language", "en")
    app = SpectrExcelApp("test", DisplayScale())
    try:
        app.build()
        messages = []
        monkeypatch.setattr(app, "log", messages.append)
        monkeypatch.setattr(app.settings, "set", lambda *args: False)
        app._layout_changed(None, "bad label")
        assert app.assay_view.layout == "parameters_only"
        assert messages == []
        app._layout_changed(None, "parameters + preview")
        assert app.assay_view.layout == "parameters_preview"
        assert messages == ["ERROR: unable to save the layout preference"]
    finally:
        app.shutdown()


def test_app_services_pending_preview_on_render_thread(dpg_context, monkeypatch, tmp_path):
    monkeypatch.setattr("spectrexcel.settings.user_config_path", lambda *args: tmp_path)
    jobs = []
    monkeypatch.setattr(SpectrExcelApp, "submit", lambda self, *args: jobs.append(args))
    app = SpectrExcelApp("test", DisplayScale())
    try:
        set_language("en")
        app.build()
        jobs.clear()  # startup update/citation tasks
        view = app.assay_view
        view.dataframe = pd.DataFrame({"#Sample": ["one"], 300: [1.0], 800: [0.25]})
        app._layout_changed(None, "parameters + preview")
        app.maintain_assay()
        assert len(jobs) == 1
        task, success, failure = jobs[0]
        app.results.put((success, task(), None))
        assert view._embedded_renderer.plot is None
        app.process_results()
        assert view._embedded_renderer.plot is not None
    finally:
        app.shutdown()
