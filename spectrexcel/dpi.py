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
