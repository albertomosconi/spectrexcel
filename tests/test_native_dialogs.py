import signal

import pytest

from spectrexcel import native_dialogs


class FakePicker:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.running = True
        self.terminated = False

    def communicate(self):
        self.running = False
        return self.stdout, self.stderr

    def poll(self):
        return None if self.running else self.returncode

    def terminate(self):
        self.terminated = True


def test_zenity_open_multiple(monkeypatch, tmp_path):
    commands = []
    monkeypatch.setattr(native_dialogs.sys, "platform", "linux")
    monkeypatch.setattr(native_dialogs.shutil, "which", lambda command: command == "zenity")

    def popen(command, **_kwargs):
        commands.append(command)
        return FakePicker(stdout="/tmp/one.KD\n/tmp/two.KD\n")

    monkeypatch.setattr(native_dialogs.subprocess, "Popen", popen)

    selected = native_dialogs.open_files(
        "Open", str(tmp_path), {"Kinetic data": ["*.KD", "*.kd"]}, True
    )

    assert selected == ["/tmp/one.KD", "/tmp/two.KD"]
    assert f"--filename={tmp_path}{native_dialogs.os.sep}" in commands[0]


@pytest.mark.parametrize("returncode", [1, -signal.SIGTERM])
def test_native_dialog_cancel_returns_no_paths(monkeypatch, tmp_path, returncode):
    monkeypatch.setattr(native_dialogs.sys, "platform", "linux")
    monkeypatch.setattr(native_dialogs.shutil, "which", lambda command: command == "zenity")
    monkeypatch.setattr(
        native_dialogs.subprocess,
        "Popen",
        lambda command, **_kwargs: FakePicker(returncode),
    )

    assert native_dialogs.open_files("Open", str(tmp_path), {"Data": ["*.txt"]}) == []
    assert native_dialogs._active_picker is None


def test_native_dialog_failure_reports_picker_error(monkeypatch, tmp_path):
    monkeypatch.setattr(native_dialogs.sys, "platform", "linux")
    monkeypatch.setattr(native_dialogs.shutil, "which", lambda command: command == "zenity")
    monkeypatch.setattr(
        native_dialogs.subprocess,
        "Popen",
        lambda command, **_kwargs: FakePicker(5, stderr="cannot open display\n"),
    )

    with pytest.raises(RuntimeError, match="cannot open display"):
        native_dialogs.open_files("Open", str(tmp_path), {"Data": ["*.txt"]})


def test_cancel_terminates_only_a_running_picker(monkeypatch):
    picker = FakePicker()
    monkeypatch.setattr(native_dialogs, "_active_picker", picker)

    native_dialogs.cancel()
    assert picker.terminated

    finished = FakePicker()
    finished.running = False
    monkeypatch.setattr(native_dialogs, "_active_picker", finished)
    native_dialogs.cancel()
    assert not finished.terminated

    monkeypatch.setattr(native_dialogs, "_active_picker", None)
    native_dialogs.cancel()


def test_missing_linux_picker_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(native_dialogs.sys, "platform", "linux")
    monkeypatch.setattr(native_dialogs.shutil, "which", lambda _command: None)

    try:
        native_dialogs.open_files("Open", str(tmp_path), {"Data": ["*.txt"]})
    except RuntimeError as error:
        assert "Zenity or KDialog" in str(error)
    else:
        raise AssertionError("missing picker should fail")
