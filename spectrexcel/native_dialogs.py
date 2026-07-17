import os
import shutil
import subprocess
import sys
from pathlib import Path


FileFilters = dict[str, list[str]]


def open_files(
    title: str, default_path: str, filters: FileFilters, multiple: bool = False
) -> list[str]:
    if sys.platform == "win32":
        return _windows_open(title, default_path, filters, multiple)
    return _linux_dialog(title, default_path, filters, multiple=multiple)


def save_file(
    title: str, default_path: str, default_filename: str, filters: FileFilters
) -> str:
    if sys.platform == "win32":
        return _windows_save(title, default_path, default_filename, filters)
    paths = _linux_dialog(
        title,
        str(Path(default_path) / default_filename),
        filters,
        save=True,
    )
    return paths[0] if paths else ""


def _linux_dialog(
    title: str,
    default_path: str,
    filters: FileFilters,
    *,
    multiple: bool = False,
    save: bool = False,
) -> list[str]:
    if shutil.which("zenity"):
        initial_path = Path(default_path).resolve()
        initial_value = str(initial_path)
        if not save and initial_path.is_dir():
            initial_value += os.sep
        command = [
            "zenity",
            "--file-selection",
            f"--title={title}",
            f"--filename={initial_value}",
        ]
        for label, patterns in filters.items():
            command.append(f"--file-filter={label} | {' '.join(patterns)}")
        if multiple:
            command.extend(["--multiple", "--separator=\n"])
        if save:
            command.extend(["--save", "--confirm-overwrite"])
    elif shutil.which("kdialog"):
        action = "--getsavefilename" if save else "--getopenfilename"
        filter_text = " | ".join(
            f"{label} ({' '.join(patterns)})" for label, patterns in filters.items()
        )
        command = ["kdialog", action, str(Path(default_path).resolve()), filter_text]
        if multiple:
            command.extend(["--multiple", "--separate-output"])
        command.extend(["--title", title])
    else:
        raise RuntimeError("install Zenity or KDialog to use the system file picker")

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode == 1:
        return []
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "system file picker failed")
    return [path for path in result.stdout.splitlines() if path]


def _windows_filter(filters: FileFilters) -> str:
    return "".join(
        f"{label}\0{';'.join(patterns)}\0" for label, patterns in filters.items()
    )


def _windows_open(
    title: str, default_path: str, filters: FileFilters, multiple: bool
) -> list[str]:
    flags = 0x00080000 | 0x00001000 | 0x00000800
    if multiple:
        flags |= 0x00000200
    selected = _windows_dialog(title, default_path, "", filters, flags, save=False)
    if not selected:
        return []
    values = selected
    if len(values) == 1:
        return values
    return [str(Path(values[0]) / name) for name in values[1:]]


def _windows_save(
    title: str, default_path: str, default_filename: str, filters: FileFilters
) -> str:
    selected = _windows_dialog(
        title,
        default_path,
        default_filename,
        filters,
        0x00080000 | 0x00000800 | 0x00000002,
        save=True,
    )
    return selected[0] if selected else ""


def _windows_dialog(
    title: str,
    default_path: str,
    default_filename: str,
    filters: FileFilters,
    flags: int,
    *,
    save: bool,
) -> list[str]:
    import ctypes
    from ctypes import wintypes

    class OpenFilename(ctypes.Structure):
        _fields_ = [
            ("lStructSize", wintypes.DWORD),
            ("hwndOwner", wintypes.HWND),
            ("hInstance", wintypes.HINSTANCE),
            ("lpstrFilter", wintypes.LPCWSTR),
            ("lpstrCustomFilter", wintypes.LPWSTR),
            ("nMaxCustFilter", wintypes.DWORD),
            ("nFilterIndex", wintypes.DWORD),
            ("lpstrFile", wintypes.LPWSTR),
            ("nMaxFile", wintypes.DWORD),
            ("lpstrFileTitle", wintypes.LPWSTR),
            ("nMaxFileTitle", wintypes.DWORD),
            ("lpstrInitialDir", wintypes.LPCWSTR),
            ("lpstrTitle", wintypes.LPCWSTR),
            ("Flags", wintypes.DWORD),
            ("nFileOffset", wintypes.WORD),
            ("nFileExtension", wintypes.WORD),
            ("lpstrDefExt", wintypes.LPCWSTR),
            ("lCustData", wintypes.LPARAM),
            ("lpfnHook", ctypes.c_void_p),
            ("lpTemplateName", wintypes.LPCWSTR),
            ("pvReserved", ctypes.c_void_p),
            ("dwReserved", wintypes.DWORD),
            ("FlagsEx", wintypes.DWORD),
        ]

    file_buffer = ctypes.create_unicode_buffer(65536)
    file_buffer.value = default_filename
    filter_buffer = ctypes.create_unicode_buffer(_windows_filter(filters) + "\0")
    ctypes.windll.user32.GetForegroundWindow.restype = wintypes.HWND
    options = OpenFilename(
        lStructSize=ctypes.sizeof(OpenFilename),
        hwndOwner=ctypes.windll.user32.GetForegroundWindow(),
        lpstrFilter=ctypes.cast(filter_buffer, wintypes.LPCWSTR),
        nFilterIndex=1,
        lpstrFile=ctypes.cast(file_buffer, wintypes.LPWSTR),
        nMaxFile=len(file_buffer),
        lpstrInitialDir=str(Path(default_path).resolve()),
        lpstrTitle=title,
        Flags=flags,
        lpstrDefExt="xlsx" if save else None,
    )
    picker = (
        ctypes.windll.comdlg32.GetSaveFileNameW
        if save
        else ctypes.windll.comdlg32.GetOpenFileNameW
    )
    picker.argtypes = [ctypes.POINTER(OpenFilename)]
    picker.restype = wintypes.BOOL
    if not picker(ctypes.byref(options)):
        error = ctypes.windll.comdlg32.CommDlgExtendedError()
        if error:
            raise OSError(f"Windows file picker failed with error 0x{error:04x}")
        return []
    return [value for value in file_buffer[:].split("\0") if value]
