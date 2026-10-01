import sys
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

from packaging.version import Version
from PyInstaller.__main__ import run as pyinstaller_run


def windows_version_info(project_version: str) -> str:
    """Generate PyInstaller's Windows resource from the package version."""
    parsed = Version(project_version)
    if parsed.epoch or len(parsed.release) > 4 or any(
        part > 65535 for part in parsed.release
    ):
        raise ValueError("Project version cannot be represented in Windows metadata")
    numeric_version = parsed.release + (0,) * (4 - len(parsed.release))
    flags = 2 if parsed.is_prerelease else 0
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numeric_version!r},
    prodvers={numeric_version!r},
    mask=0x3f,
    flags={flags},
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'Alberto Mosconi'),
        StringStruct('FileDescription', 'SpectrExcel'),
        StringStruct('FileVersion', {project_version!r}),
        StringStruct('InternalName', 'spectrexcel'),
        StringStruct('OriginalFilename', 'spectrexcel-windows-x86_64.exe'),
        StringStruct('ProductName', 'SpectrExcel'),
        StringStruct('ProductVersion', {project_version!r})
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def install():
    if sys.platform == "linux":
        spec = (
            Path(__file__).parent.parent
            / "packaging"
            / "linux"
            / "spectrexcel.spec"
        )
        pyinstaller_run([str(spec), "--clean", "--noconfirm"])
        return

    PATH_ICON = str(Path(__file__).parent.absolute() / "icon.ico")
    PATH_FONTS = str(Path(__file__).parent.absolute() / "fonts")
    PATH_MANIFEST = str(
        Path(__file__).parent.parent.absolute()
        / "packaging"
        / "windows"
        / "spectrexcel.manifest"
    )
    arguments = [
        str(Path(__file__).parent.absolute() / "main.py"),
        "--name",
        "spectrexcel",
        "--clean",
        "--onefile",
        "--noconsole",  # don't open console window
        "--collect-binaries",
        "dearpygui",
        "--copy-metadata",
        "spectrexcel",
        "--optimize",
        "0",
        "--add-data",
        f"{PATH_ICON}:.",
        "--add-data",
        f"{PATH_FONTS}:fonts",
        "--icon",
        PATH_ICON,
        "--manifest",
        PATH_MANIFEST,
    ]
    with TemporaryDirectory(prefix="spectrexcel-build-") as resource_dir:
        resource_path = Path(resource_dir) / "version-info.txt"
        resource_path.write_text(
            windows_version_info(version("spectrexcel")), encoding="utf-8"
        )
        pyinstaller_run(arguments + ["--version-file", str(resource_path)])
