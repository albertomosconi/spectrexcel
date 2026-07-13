from pathlib import Path

from PyInstaller.__main__ import run as pyinstaller_run


def install():
    PATH_ICON = str(Path(__file__).parent.absolute() / "icon.ico")
    PATH_FONTS = str(Path(__file__).parent.absolute() / "fonts")
    PATH_MANIFEST = str(
        Path(__file__).parent.parent.absolute()
        / "packaging"
        / "windows"
        / "spectrexcel.manifest"
    )
    pyinstaller_run(
        [
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
    )
