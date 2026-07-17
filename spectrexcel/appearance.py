import subprocess
import sys


THEME_OPTIONS = ("System", "Light", "Dark")


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
