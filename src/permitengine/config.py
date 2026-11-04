"""Settings. One file, each entry with its limits. A value outside its limits stops the run, with no silent clamping."""
from dataclasses import dataclass
from pathlib import Path

import yaml

from .workspace import EngineError


def _check_limits(key, value, limits):
    if not limits:
        return
    if "allowed" in limits and value not in limits["allowed"]:
        raise EngineError(f"setting {key} = {value} is not one of {limits['allowed']}")
    values = value if isinstance(value, list) else [value]
    for item in values:
        if not isinstance(item, (int, float)):
            continue
        low, high = limits.get("min"), limits.get("max")
        if (low is not None and item < low) or (high is not None and item > high):
            raise EngineError(f"setting {key} = {item} is outside its limits {limits}")


@dataclass(frozen=True)
class Settings:
    entries: dict  # key -> entry dict

    def get(self, key, default=...):
        if key in self.entries:
            return self.entries[key]["value"]
        if default is ...:
            raise EngineError(f"setting {key} is not in settings/settings.yaml")
        return default

    def anchors(self, scale: str) -> list:
        return list(self.get(f"risk.anchors.{scale}"))


def load_settings(path: Path) -> Settings:
    if not Path(path).exists():
        raise EngineError(f"{path} does not exist")
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    rows = raw["settings"] if isinstance(raw, dict) and "settings" in raw else raw
    if not isinstance(rows, list):
        raise EngineError(f"{path} must hold a list of settings")
    entries = {}
    for row in rows:
        _check_limits(row["key"], row.get("value"), row.get("limits"))
        entries[row["key"]] = row
    return Settings(entries)
