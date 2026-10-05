import ast
from importlib.metadata import version
from pathlib import Path

import pytest

from spectrexcel import pyinstaller


def read_version_info(text):
    """Inspect the generated PyInstaller resource without Windows-only imports."""
    tree = ast.parse(text, mode="eval")
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    fixed = next(node for node in calls if isinstance(node.func, ast.Name) and node.func.id == "FixedFileInfo")
    fixed_values = {
        keyword.arg: ast.literal_eval(keyword.value) for keyword in fixed.keywords
    }
    strings = {
        ast.literal_eval(node.args[0]): ast.literal_eval(node.args[1])
        for node in calls
        if isinstance(node.func, ast.Name) and node.func.id == "StringStruct"
    }
    return fixed_values, strings


@pytest.mark.parametrize(
    "project_version, numeric_version, flags",
    [
        ("1.6.0", (1, 6, 0, 0), 0),
        ("2.10", (2, 10, 0, 0), 0),
        ("1.2.3.4", (1, 2, 3, 4), 0),
        ("2.0.0rc1", (2, 0, 0, 0), 2),
    ],
)
def test_windows_metadata_preserves_release_version(project_version, numeric_version, flags):
    fixed, strings = read_version_info(pyinstaller.windows_version_info(project_version))

    assert fixed["filevers"] == numeric_version
    assert fixed["prodvers"] == numeric_version
    assert fixed["flags"] == flags
    assert strings["FileVersion"] == project_version
    assert strings["ProductVersion"] == project_version
    assert strings["ProductName"] == "SpectrExcel"
    assert strings["FileDescription"] == "SpectrExcel"
    assert strings["OriginalFilename"] == "spectrexcel-windows-x86_64.exe"


@pytest.mark.parametrize("project_version", ["1.2.3.4.5", "65536.0.0", "1!1.2.3"])
def test_windows_metadata_rejects_versions_not_representable_in_windows(project_version):
    with pytest.raises(ValueError):
        pyinstaller.windows_version_info(project_version)


def test_windows_build_passes_current_version_resource_to_pyinstaller(monkeypatch):
    resources = []

    def capture_build(arguments):
        assert "--version-file" in arguments
        resource_path = Path(arguments[arguments.index("--version-file") + 1])
        resources.append(resource_path.read_text(encoding="utf-8"))

    monkeypatch.setattr(pyinstaller.sys, "platform", "win32")
    monkeypatch.setattr(pyinstaller, "pyinstaller_run", capture_build)

    pyinstaller.install()

    assert len(resources) == 1
    fixed, strings = read_version_info(resources[0])
    assert strings["ProductVersion"] == version("spectrexcel")
    assert fixed["filevers"] == fixed["prodvers"]
