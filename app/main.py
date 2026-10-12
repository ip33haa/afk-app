"""Tray app: watch the camera, lock when you leave, unlock when you return."""

from __future__ import annotations

import ctypes
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes

import pystray
from PIL import Image, ImageDraw

from app.camera import CameraService
from app.config import Config
from app.enroll_ui import SettingsWindow
from app.face import FaceEngine
from app.liveness import BlinkDetector
from app.logging_setup import setup
from app.paths import credential_provider_registered
from app.presence import PresenceEngine
from app.screen_lock import ScreenLock
from app.secure_store import SecureStore
from app.session import SessionMonitor
from app.unlock_client import UnlockClient
from app.verses import lock_screen_text

_ERROR_ALREADY_EXISTS = 183
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateMutexW.restype = wintypes.HANDLE


class App:
    def __init__(self) -> None:
        self._log = setup()
        self.config = Config.load()
        self.face = FaceEngine(self.config.match_threshold)
        self.blink = BlinkDetector()
        self.camera = CameraService(self.config.camera_index)
        self.session = SessionMonitor()
        self.store = SecureStore()
        self.unlock = UnlockClient(self.store)
        self.engine = self._new_engine()
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._status = "Starting"
        self._logged_state = ""
        self._provider_installed = credential_provider_registered()
        self.root: tk.Tk | None = None
        self.screen: ScreenLock | None = None
        self.icon: pystray.Icon | None = None
        self._settings: SettingsWindow | None = None
        self._paused_before_settings = False
        self._did_shutdown = False
        self._icons = {
            "green": _circle((40, 160, 80)),
            "yellow": _circle((210, 160, 40)),
            "red": _circle((180, 50, 50)),
            "gray": _circle((90, 90, 90)),
            "blue": _circle((50, 110, 180)),
        }
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.session.start()
        self.camera.start()
        self._thread = threading.Thread(target=self._loop, name="afk-monitor", daemon=True)
        self._thread.start()
        self.icon = pystray.Icon(
            "AFK",
            self._icons["gray"],
            "AFK",
            menu=pystray.Menu(
                pystray.MenuItem(lambda _: self._status, None, enabled=False),
                pystray.MenuItem(lambda _: "Resume" if self._pause.is_set() else "Pause", self._toggle_pause),
                pystray.MenuItem("Set up face and PIN", self._open_settings),
                pystray.MenuItem("Lock now", self._lock_now),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._quit),
            ),
        )
        if self.config.require_blink and not self.blink.available:
            self._log.info("blink detection unavailable")
        self.icon.run_detached()
        self._log.info("AFK started")

    def bind(self, root: tk.Tk) -> None:
        self.root = root
        self.screen = ScreenLock(root, self.store)

    def shutdown(self) -> None:
        if self._did_shutdown:
            return
        self._did_shutdown = True
        if self.screen is not None:
            self.screen.unlock()
        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=3)
        self.camera.stop()
        self.session.stop()
        icon = self.icon
        self.icon = None
        if icon is not None:
            icon.stop()
        self._log.info("AFK stopped")

    def _new_engine(self) -> PresenceEngine:
        return PresenceEngine(
            grace_seconds=self.config.grace_seconds,
            match_hold_seconds=self.config.match_hold_seconds,
            cooldown_seconds=self.config.cooldown_seconds,
            require_blink=self.config.require_blink,
        )

    def _loop(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self._tick()
            except Exception:
                self._log.exception("monitor tick failed")
            remaining = 0.2 - (time.monotonic() - started)
            if remaining > 0:
                self._stop.wait(remaining)

    def _tick(self) -> None:
        if self._pause.is_set():
            self._set_status("Paused", "gray")
            return
        if not self.config.monitoring:
            self._set_status("Setup is not finished", "gray")
            return
        if not self.face.ready:
            self._set_status(self.face.error or "Face models are missing. Run install.ps1.", "yellow")
            return
        if not self.face.has_enrollment():
            self._set_status("Enroll your face to start", "gray")
            return
        frame = self.camera.latest()
        if frame is None:
            self._set_status(self.camera.error or "Waiting for the camera", "yellow")
            return

        matched, _score = self.face.matches(frame)
        if self.config.require_blink and matched and self.engine.state == "watching_locked":
            blinked = self.blink.update(frame)
        else:
            blinked = self.blink.latched if self.config.require_blink else True

        covered = self.screen is not None and self.screen.is_locked()
        windows_locked = self.session.is_locked()
        result = self.engine.update(
            enrolled_face_present=matched,
            blinked=blinked,
            session_locked=covered or windows_locked,
            now=time.monotonic(),
        )
        if result.clear_blink:
            self.blink.reset()
        status = result.status
        color = _color_for(self.engine.state)
        if self.engine.state == "watching_locked" and self.config.require_blink and not self.blink.available:
            status = "Locked — blink detection is unavailable. Turn the blink check off in setup."
        elif self.engine.state == "watching_locked" and windows_locked and not self._provider_installed:
            status = "Windows is locked. Type your password. Camera unlock cannot dismiss the Windows lock screen."
        elif self.screen is not None and self.screen.is_locked():
            status = self.screen.message
        self._set_status(status, color)
        if self.engine.state != self._logged_state or result.action:
            self._log.info("state=%s action=%s", self.engine.state, result.action or "-")
            self._logged_state = self.engine.state
        if result.action == "lock":
            self._lock_screen()
        elif result.action == "unlock":
            self._unlock_screen()

    def _lock_screen(self) -> None:
        if self._provider_installed:
            self.session.lock()
            return
        if self.screen is None:
            return
        self.screen.lock(self._lock_text())
        self._log.info("screen locked")

    def _lock_text(self) -> str:
        return lock_screen_text(
            show_verse=self.config.show_verse,
            require_blink=self.config.require_blink,
        )

    def _unlock_screen(self) -> None:
        if self.screen is not None and self.screen.is_locked() and not self.session.is_locked():
            self.screen.unlock()
            self.engine.note_unlock_result("accepted", time.monotonic())
            self._log.info("screen unlocked")
            return
        self._request_unlock()

    def _request_unlock(self) -> None:
        if not self._provider_installed:
            self._log.info("unlock skipped; credential provider is not registered")
            self.engine.note_unlock_result("rejected", time.monotonic())
            return
        if not self.store.has_secret():
            self._log.info("unlock skipped; password is not saved")
            self.engine.note_unlock_result("rejected", time.monotonic())
            return
        outcome = self.unlock.try_unlock()
        self._log.info("unlock result=%s", outcome)
        self.engine.note_unlock_result(outcome, time.monotonic())

    def _set_status(self, text: str, color: str) -> None:
        changed = text != self._status
        self._status = text
        icon = self.icon
        if icon is None:
            return
        icon.title = f"AFK — {text}"
        if changed:
            icon.icon = self._icons[color]
            try:
                icon.update_menu()
            except Exception:
                pass

    def _toggle_pause(self, _icon=None, _item=None) -> None:
        if self._pause.is_set():
            self._pause.clear()
            self.engine = self._new_engine()
            if self._is_covered():
                self.engine.state = "watching_locked"
            self._log.info("monitoring resumed")
        else:
            self._pause.set()
            self._log.info("monitoring paused")
        if self.icon is not None:
            self.icon.update_menu()

    def _open_settings(self, _icon=None, _item=None) -> None:
        if self.root is None:
            return
        self.root.after(0, self._show_settings)

    def _show_settings(self) -> None:
        if self._settings is not None and not self._settings._closed:
            self._settings.window.lift()
            return
        self._paused_before_settings = self._pause.is_set()
        self._pause.set()
        self._settings = SettingsWindow(
            self.root,
            self.camera,
            self.face,
            self.config,
            self._apply_settings,
        )
        self._settings.window.bind("<Destroy>", self._settings_closed, add="+")

    def _settings_closed(self, event=None) -> None:
        window = self._settings.window if self._settings is not None else None
        if event is not None and window is not None and event.widget is not window:
            return
        if not self._paused_before_settings:
            self._pause.clear()
        self.engine = self._new_engine()
        if self._is_covered():
            self.engine.state = "watching_locked"

    def _is_covered(self) -> bool:
        if self.screen is not None and self.screen.is_locked():
            return True
        return self.session.is_locked()

    def _apply_settings(self) -> None:
        self.config = Config.load()
        self.face.threshold = self.config.match_threshold
        self.face.reload()
        self.engine = self._new_engine()
        self._provider_installed = credential_provider_registered()
        self._log.info("setup saved; monitoring on")

    def _lock_now(self, _icon=None, _item=None) -> None:
        if self._provider_installed:
            if not self.session.is_locked():
                self.session.lock()
                self._log.info("locked from the menu")
            return
        if self.screen is not None and not self.screen.is_locked():
            self.screen.lock(self._lock_text())
            self._log.info("screen locked from the menu")

    def _quit(self, _icon=None, _item=None) -> None:
        self.shutdown()
        if self.root is not None:
            self.root.after(0, self.root.quit)


def _circle(color: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", (64, 64), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 56, 56), fill=color)
    return image


def _color_for(state: str) -> str:
    if state == "armed":
        return "green"
    if state in ("locking", "watching_locked", "unlocking"):
        return "red"
    if state == "cooldown":
        return "blue"
    return "gray"


def _already_running() -> bool:
    handle = _kernel32.CreateMutexW(None, False, "Local\\AFKCameraLock")
    if not handle:
        return False
    return ctypes.get_last_error() == _ERROR_ALREADY_EXISTS


def main() -> None:
    if _already_running():
        setup().info("AFK is already running")
        return
    app = App()
    root = tk.Tk()
    root.withdraw()
    app.bind(root)
    app.start()
    if not app.config.monitoring or not app.face.has_enrollment():
        root.after(600, app._show_settings)
    try:
        root.mainloop()
    finally:
        app.shutdown()


if __name__ == "__main__":
    main()
