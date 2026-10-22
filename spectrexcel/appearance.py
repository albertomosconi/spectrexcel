import subprocess
import sys


THEME_OPTIONS = ("System", "Light", "Dark")

SEMANTIC_TEXT_COLORS = {
    "Dark": {"accent": (104, 190, 255), "muted": (150, 150, 150)},
    "Light": {"accent": (24, 91, 138), "muted": (95, 100, 108)},
}

THEME_COLORS = {
    "Dark": {
        "Text": (235, 235, 235),
        "TextDisabled": (135, 135, 135),
        "WindowBg": (24, 27, 32),
        "ChildBg": (24, 27, 32, 0),
        "PopupBg": (30, 34, 40),
        "Border": (65, 70, 78),
        "FrameBg": (42, 47, 55),
        "FrameBgHovered": (52, 59, 69),
        "FrameBgActive": (62, 70, 82),
        "Button": (36, 91, 130),
        "ButtonHovered": (46, 116, 163),
        "ButtonActive": (31, 78, 111),
        "Header": (36, 91, 130),
        "HeaderHovered": (46, 116, 163),
        "HeaderActive": (31, 78, 111),
        "CheckMark": (104, 190, 255),
        "Separator": (65, 70, 78),
        "ScrollbarBg": (24, 27, 32),
        "ScrollbarGrab": (72, 78, 88),
        "TableBorderStrong": (65, 70, 78),
        "TableBorderLight": (50, 55, 63),
    },
    "Light": {
        "Text": (255, 255, 255),
        "TextDisabled": (205, 215, 222),
        "WindowBg": (244, 246, 248),
        "ChildBg": (244, 246, 248, 0),
        "PopupBg": (252, 252, 253),
        "Border": (180, 185, 192),
        "FrameBg": (36, 91, 130),
        "FrameBgHovered": (46, 116, 163),
        "FrameBgActive": (31, 78, 111),
        "Button": (36, 91, 130),
        "ButtonHovered": (46, 116, 163),
        "ButtonActive": (31, 78, 111),
        "Header": (36, 91, 130),
        "HeaderHovered": (46, 116, 163),
        "HeaderActive": (31, 78, 111),
        "CheckMark": (255, 255, 255),
        "Separator": (180, 185, 192),
        "ScrollbarBg": (235, 238, 241),
        "ScrollbarGrab": (170, 176, 184),
        "TableBorderStrong": (180, 185, 192),
        "TableBorderLight": (210, 214, 220),
    },
}

# The plot's built-in context menu draws on PopupBg with the base colors,
# which are white-on-blue in the Light theme.
PLOT_MENU_COLORS = {
    "Light": {
        "Text": (30, 34, 40),
        "TextDisabled": (95, 100, 108),
        "FrameBg": (222, 228, 235),
        "FrameBgHovered": (205, 216, 228),
        "FrameBgActive": (190, 205, 220),
        "CheckMark": (36, 91, 130),
        "Header": (200, 220, 236),
        "HeaderHovered": (184, 209, 230),
        "HeaderActive": (166, 197, 222),
    },
}

DISABLED_BUTTON_COLORS = {
    "Dark": {
        "Text": (150, 150, 150),
        "TextDisabled": (150, 150, 150),
        "Button": (50, 55, 63),
        "ButtonHovered": (50, 55, 63),
        "ButtonActive": (50, 55, 63),
    },
    "Light": {
        "Text": (95, 100, 108),
        "TextDisabled": (95, 100, 108),
        "Button": (210, 214, 220),
        "ButtonHovered": (210, 214, 220),
        "ButtonActive": (210, 214, 220),
    },
}


def system_theme(platform: str | None = None) -> str:
    platform = platform or sys.platform
    if platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                return "Light" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] else "Dark"
        except (ImportError, OSError):
            pass
    elif platform.startswith("linux"):
        try:
            result = subprocess.run(
                [
                    "gsettings",
                    "get",
                    "org.gnome.desktop.interface",
                    "color-scheme",
                ],
                capture_output=True,
                text=True,
                timeout=1,
                check=True,
            )
            return "Dark" if "dark" in result.stdout.lower() else "Light"
        except (OSError, subprocess.SubprocessError):
            pass
    return "Dark"


def resolve_theme(preference: str, platform: str | None = None) -> str:
    if preference not in THEME_OPTIONS:
        preference = "System"
    return system_theme(platform) if preference == "System" else preference
