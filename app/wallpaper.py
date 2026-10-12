"""The picture Windows is already using for the desktop."""

from __future__ import annotations

import os
import winreg
from pathlib import Path


def lock_image_path() -> Path | None:
    """Return the current wallpaper, if Windows has one on disk."""
    wallpaper = _registry_wallpaper()
    if wallpaper is not None and wallpaper.is_file():
        return wallpaper
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    transcoded = Path(appdata) / "Microsoft" / "Windows" / "Themes" / "TranscodedWallpaper"
    if transcoded.is_file():
        return transcoded
    return None


def _registry_wallpaper() -> Path | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as key:
            value, _kind = winreg.QueryValueEx(key, "WallPaper")
    except OSError:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value)
