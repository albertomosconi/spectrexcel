from pathlib import Path

from spectrexcel.assays.cinetiche import Cinetiche
from spectrexcel.assays.famiglia_di_spettri import FamigliaDiSpettri
from spectrexcel.assays.titolazione import BindingTitolazione
from spectrexcel.assays.view import AssayView, WorkflowControls
from spectrexcel.dpi import DisplayScale


class WorkflowView(AssayView):
    workflow_controls = WorkflowControls(
        upload="test.upload",
        export="test.export",
        status="test.status",
        load_extras=("test.reorder",),
        export_extras=("test.upload",),
    )


def workflow_view():
    submitted = {}
    messages = []

    def submit(task, on_success, on_error):
        submitted.update(
            task=task,
            on_success=on_success,
            on_error=on_error,
        )

    view = WorkflowView(messages.append, submit, None, DisplayScale())
    return view, submitted, messages


def assay_view():
    return AssayView(lambda _message: None, lambda *_args: None, None, DisplayScale())


def test_assays_declare_workflow_controls():
    assert Cinetiche.workflow_controls == WorkflowControls(
        upload="kinetics.upload",
        export="kinetics.export",
        status="kinetics.files",
        load_extras=("kinetics.reorder",),
    )
    assert BindingTitolazione.workflow_controls == WorkflowControls(
        upload="binding.upload",
        export="binding.export",
        status="binding.file",
        export_extras=("binding.upload",),
    )
    assert FamigliaDiSpettri.workflow_controls == WorkflowControls(
        upload="spectra.upload",
        export="spectra.export",
        status="spectra.file",
    )


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


def test_submit_load_applies_busy_state_and_restores_standard_controls(monkeypatch):
    configured = []
    values = []
    monkeypatch.setattr(
        "spectrexcel.assays.view.dpg.configure_item",
        lambda tag, **values: configured.append((tag, values)),
    )
    monkeypatch.setattr(
        "spectrexcel.assays.view.dpg.set_value",
        lambda tag, value: values.append((tag, value)),
    )
    view, submitted, _messages = workflow_view()
    received = []

    view.submit_load(
        lambda: "parsed",
        received.append,
        loading_text="Loading files...",
        failure_text="Failed to load files",
    )

    assert configured == [
        ("test.upload", {"enabled": False}),
        ("test.export", {"enabled": False}),
        ("test.reorder", {"enabled": False}),
    ]
    assert values == [("test.status", "Loading files...")]

    submitted["on_success"]("parsed")

    assert received == ["parsed"]
    assert configured[-2:] == [
        ("test.upload", {"enabled": True}),
        ("test.export", {"enabled": True}),
    ]
    assert ("test.reorder", {"enabled": True}) not in configured


def test_submit_load_failure_preserves_disabled_export(monkeypatch):
    configured = []
    values = []
    monkeypatch.setattr(
        "spectrexcel.assays.view.dpg.configure_item",
        lambda tag, **values: configured.append((tag, values)),
    )
    monkeypatch.setattr(
        "spectrexcel.assays.view.dpg.set_value",
        lambda tag, value: values.append((tag, value)),
    )
    view, submitted, messages = workflow_view()

    view.submit_load(
        lambda: None,
        lambda _result: None,
        loading_text="Loading files...",
        failure_text="Failed to load files",
    )
    submitted["on_error"](ValueError("bad file"))

    assert configured[-1] == ("test.upload", {"enabled": True})
    assert ("test.export", {"enabled": True}) not in configured
    assert ("test.reorder", {"enabled": True}) not in configured
    assert values[-1] == ("test.status", "Failed to load files")
    assert messages == ["ERROR: bad file"]


def test_submit_export_restores_controls_and_logs_success(monkeypatch):
    configured = []
    monkeypatch.setattr(
        "spectrexcel.assays.view.dpg.configure_item",
        lambda tag, **values: configured.append((tag, values)),
    )
    view, submitted, messages = workflow_view()

    view.submit_export(lambda: None)

    assert configured == [
        ("test.export", {"enabled": False}),
        ("test.upload", {"enabled": False}),
    ]
    assert messages == ["generating excel file..."]

    submitted["on_success"](None)

    assert configured[-2:] == [
        ("test.export", {"enabled": True}),
        ("test.upload", {"enabled": True}),
    ]
    assert messages[-1] == "excel file saved successfully"


def test_submit_export_restores_controls_and_logs_error(monkeypatch):
    configured = []
    monkeypatch.setattr(
        "spectrexcel.assays.view.dpg.configure_item",
        lambda tag, **values: configured.append((tag, values)),
    )
    view, submitted, messages = workflow_view()

    view.submit_export(lambda: None)
    submitted["on_error"](OSError("disk full"))

    assert configured[-2:] == [
        ("test.export", {"enabled": True}),
        ("test.upload", {"enabled": True}),
    ]
    assert messages[-1] == "ERROR: disk full"


def test_submit_suppresses_callbacks_after_dispose():
    submitted = {}
    received = []

    def submit(_task, on_success, on_error):
        submitted.update(on_success=on_success, on_error=on_error)

    view = AssayView(lambda _message: None, submit, None, DisplayScale())
    view.submit(lambda: None, received.append, received.append)
    view.dispose()

    submitted["on_success"]("result")
    submitted["on_error"](ValueError("failure"))

    assert received == []


def test_submit_load_suppresses_lifecycle_effects_after_dispose(monkeypatch):
    configured = []
    values = []
    monkeypatch.setattr(
        "spectrexcel.assays.view.dpg.configure_item",
        lambda tag, **values: configured.append((tag, values)),
    )
    monkeypatch.setattr(
        "spectrexcel.assays.view.dpg.set_value",
        lambda tag, value: values.append((tag, value)),
    )
    view, submitted, messages = workflow_view()
    received = []

    view.submit_load(
        lambda: "parsed",
        received.append,
        loading_text="Loading files...",
        failure_text="Failed to load files",
    )
    view.dispose()
    configured.clear()
    values.clear()
    messages.clear()

    submitted["on_success"]("parsed")
    submitted["on_error"](ValueError("bad file"))

    assert received == []
    assert configured == []
    assert values == []
    assert messages == []


def test_submit_export_suppresses_lifecycle_effects_after_dispose(monkeypatch):
    configured = []
    values = []
    monkeypatch.setattr(
        "spectrexcel.assays.view.dpg.configure_item",
        lambda tag, **values: configured.append((tag, values)),
    )
    monkeypatch.setattr(
        "spectrexcel.assays.view.dpg.set_value",
        lambda tag, value: values.append((tag, value)),
    )
    view, submitted, messages = workflow_view()

    view.submit_export(lambda: None)
    view.dispose()
    configured.clear()
    values.clear()
    messages.clear()

    submitted["on_success"](None)
    submitted["on_error"](OSError("disk full"))

    assert configured == []
    assert values == []
    assert messages == []
