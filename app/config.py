"""User settings. The password is never stored in this file."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from app.paths import data_dir


@dataclass
class Config:
    grace_seconds: float = 8.0
    cooldown_seconds: float = 8.0
    match_hold_seconds: float = 1.0
    require_blink: bool = True
    match_threshold: float = 0.45
    camera_index: int = 0
    monitoring: bool = False
    start_with_windows: bool = True
    show_verse: bool = False

    @classmethod
    def load(cls) -> "Config":
        path = data_dir() / "config.json"
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        cfg = cls()
        try:
            if "grace_seconds" in raw:
                cfg.grace_seconds = _clamp(float(raw["grace_seconds"]), 3.0, 120.0)
            if "cooldown_seconds" in raw:
                cfg.cooldown_seconds = _clamp(float(raw["cooldown_seconds"]), 3.0, 60.0)
            if "match_hold_seconds" in raw:
                cfg.match_hold_seconds = _clamp(float(raw["match_hold_seconds"]), 0.4, 5.0)
            if "require_blink" in raw:
                cfg.require_blink = bool(raw["require_blink"])
            if "match_threshold" in raw:
                cfg.match_threshold = _clamp(float(raw["match_threshold"]), 0.3, 0.9)
            if "camera_index" in raw:
                cfg.camera_index = max(0, int(raw["camera_index"]))
            if "monitoring" in raw:
                cfg.monitoring = bool(raw["monitoring"])
            if "start_with_windows" in raw:
                cfg.start_with_windows = bool(raw["start_with_windows"])
            if "show_verse" in raw:
                cfg.show_verse = bool(raw["show_verse"])
        except (TypeError, ValueError):
            return cls()
        return cfg

    def save(self) -> None:
        path = data_dir() / "config.json"
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))
