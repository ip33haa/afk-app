"""Start AFK when Windows signs in."""

from __future__ import annotations

from app.paths import is_frozen, project_root, pythonw_path, startup_cmd_path


def set_start_with_windows(enabled: bool) -> None:
    path = startup_cmd_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exe = pythonw_path()
    # cmd.exe reads this file with the system ANSI code page.
    if is_frozen():
        text = f'@echo off\r\ncd /d "{exe.parent}"\r\nstart "" "{exe}"\r\n'
    else:
        root = project_root()
        text = f'@echo off\r\ncd /d "{root}"\r\nstart "" "{exe}" -m app\r\n'
    path.write_bytes(text.encode("mbcs", errors="replace"))


def starts_with_windows() -> bool:
    return startup_cmd_path().exists()
