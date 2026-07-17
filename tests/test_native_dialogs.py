import subprocess

from spectrexcel import native_dialogs


def test_zenity_open_multiple(monkeypatch, tmp_path):
    commands = []
    monkeypatch.setattr(native_dialogs.sys, "platform", "linux")
    monkeypatch.setattr(native_dialogs.shutil, "which", lambda command: command == "zenity")

    def run(command, **_kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(
            command, 0, stdout="/tmp/one.KD\n/tmp/two.KD\n"
        )

    monkeypatch.setattr(native_dialogs.subprocess, "run", run)

    selected = native_dialogs.open_files(
        "Open", str(tmp_path), {"Kinetic data": ["*.KD", "*.kd"]}, True
    )

    assert selected == ["/tmp/one.KD", "/tmp/two.KD"]
    assert f"--filename={tmp_path}/" in commands[0]


def test_native_dialog_cancel_returns_no_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(native_dialogs.sys, "platform", "linux")
    monkeypatch.setattr(native_dialogs.shutil, "which", lambda command: command == "zenity")
    monkeypatch.setattr(
        native_dialogs.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 1, stdout=""),
    )

    assert native_dialogs.open_files("Open", str(tmp_path), {"Data": ["*.txt"]}) == []


def test_missing_linux_picker_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(native_dialogs.sys, "platform", "linux")
    monkeypatch.setattr(native_dialogs.shutil, "which", lambda _command: None)

    try:
        native_dialogs.open_files("Open", str(tmp_path), {"Data": ["*.txt"]})
    except RuntimeError as error:
        assert "Zenity or KDialog" in str(error)
    else:
        raise AssertionError("missing picker should fail")
