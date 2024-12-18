from pathlib import Path

from PyInstaller.__main__ import run as pyinstaller_run


def install():
    PATH_ICON = str(Path(__file__).parent.absolute() / "icon.ico")
    pyinstaller_run(
        [
            str(Path(__file__).parent.absolute() / "main.py"),
            "--name",
            "spectrexcel",
            "--onefile",
            "--noconsole",  # don't open console window
            "--optimize",
            "0",
            "--add-data",
            f"{PATH_ICON}:.",
            "--icon",
            PATH_ICON,
        ]
    )
