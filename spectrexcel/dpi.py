import sys
from dataclasses import dataclass


BASE_DPI = 96

UI_SCALE_OPTIONS: tuple[float, ...] = (0.5, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5)
DEFAULT_UI_SCALE = 1.0


def resolve_ui_scale(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return DEFAULT_UI_SCALE
    scale = float(value)
    return scale if scale in UI_SCALE_OPTIONS else DEFAULT_UI_SCALE


def ui_scale_label(scale: float) -> str:
    return f"{round(scale * 100)}%"


@dataclass(frozen=True)
class DisplayScale:
    factor: float = 1.0

    def scaled(self, multiplier: float) -> "DisplayScale":
        return DisplayScale(self.factor * multiplier)

    def pixels(self, value: int | float) -> int:
        if value in (0, -1):
            return int(value)
        scaled = value * self.factor
        return int(scaled + 0.5) if scaled >= 0 else int(scaled - 0.5)

    def logical_pixels(self, value: int | float) -> int:
        logical = value / self.factor
        return int(logical + 0.5) if logical >= 0 else int(logical - 0.5)

    def position(self, value: list[int] | tuple[int, int]) -> tuple[int, int]:
        return self.pixels(value[0]), self.pixels(value[1])


def configure_display_scale(platform: str | None = None) -> DisplayScale:
    if (platform or sys.platform) != "win32":
        return DisplayScale()

    import ctypes

    user32 = ctypes.windll.user32
    try:
        # The packaged application also declares this in its manifest. This call
        # provides equivalent behavior when running directly from Python.
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            user32.SetProcessDPIAware()

    try:
        dpi = user32.GetDpiForSystem()
    except (AttributeError, OSError):
        user32.GetDC.restype = ctypes.c_void_p
        user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        gdi32 = ctypes.windll.gdi32
        gdi32.GetDeviceCaps.argtypes = [ctypes.c_void_p, ctypes.c_int]
        device_context = user32.GetDC(0)
        try:
            dpi = gdi32.GetDeviceCaps(device_context, 88)
        finally:
            user32.ReleaseDC(0, device_context)

    return DisplayScale(dpi / BASE_DPI if dpi > 0 else 1.0)


Rect = tuple[int, int, int, int]


def fit_to_work_area(
    position: tuple[int, int],
    size: tuple[int, int],
    work_area: Rect,
    title_bar: tuple[int, int],
) -> tuple[int, int]:
    """Keep the window where it is if its title bar can still be grabbed,
    otherwise move it fully inside the work area (top-left when too large)."""
    x, y = position
    width, height = size
    left, top, right, bottom = work_area
    grab_width, grab_height = title_bar
    overlap = min(x + width, right) - max(x, left)
    if overlap >= min(grab_width, width) and top <= y <= bottom - grab_height:
        return x, y
    x = max(left, min(x, right - width))
    y = max(top, min(y, bottom - height))
    return x, y


def nearest_work_area(rect: Rect, platform: str | None = None) -> Rect | None:
    """Work area of the monitor nearest to ``rect``, in physical pixels.

    Only Windows restores the saved position; elsewhere the window manager
    places the window, so ``None`` is returned.
    """
    if (platform or sys.platform) != "win32":
        return None

    import ctypes
    from ctypes import wintypes

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    user32 = ctypes.windll.user32
    user32.MonitorFromRect.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD]
    user32.MonitorFromRect.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    monitor_defaulttonearest = 2
    try:
        monitor = user32.MonitorFromRect(
            ctypes.byref(wintypes.RECT(*rect)), monitor_defaulttonearest
        )
        info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
    except (AttributeError, OSError):
        return None
    work = info.rcWork
    return work.left, work.top, work.right, work.bottom
