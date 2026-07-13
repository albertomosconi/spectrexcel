import json
from pathlib import Path
from typing import Any

from platformdirs import user_config_path


class Settings:
    def __init__(self) -> None:
        self.path = user_config_path("spectrexcel", "magichemistry") / "settings.json"
        self._values: dict[str, Any] = {}
        try:
            values = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(values, dict):
                self._values = values
        except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError, OSError):
            pass

    def get(self, key: str, default: Any) -> Any:
        value = self._values.get(key, default)
        if isinstance(default, bool):
            return value if isinstance(value, bool) else default
        if not isinstance(value, type(default)):
            return default
        return value

    def set(self, key: str, value: Any) -> bool:
        self._values[key] = value
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_suffix(".tmp")
            temporary_path.write_text(
                json.dumps(self._values, indent=2, sort_keys=True), encoding="utf-8"
            )
            temporary_path.replace(self.path)
        except OSError:
            return False
        return True
