"""Windows lock state and LockWorkStation."""

from __future__ import annotations

import ctypes
import logging
import threading
import time
from ctypes import wintypes

DESKTOP_SWITCHDESKTOP = 0x0100
ERROR_ACCESS_DENIED = 5
ERROR_CLASS_ALREADY_EXISTS = 1410
WM_CLOSE = 0x0010
WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8
NOTIFY_FOR_THIS_SESSION = 0
PM_REMOVE = 0x0001
HWND_MESSAGE = wintypes.HWND(-3)

_LRESULT = ctypes.c_ssize_t
_WNDPROC = ctypes.WINFUNCTYPE(
    _LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class _WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", _WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_wtsapi = ctypes.WinDLL("wtsapi32", use_last_error=True)

_user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_user32.OpenInputDesktop.restype = wintypes.HANDLE
_user32.CloseDesktop.argtypes = [wintypes.HANDLE]
_user32.CloseDesktop.restype = wintypes.BOOL
_user32.LockWorkStation.argtypes = []
_user32.LockWorkStation.restype = wintypes.BOOL
_user32.RegisterClassW.argtypes = [ctypes.POINTER(_WNDCLASSW)]
_user32.RegisterClassW.restype = wintypes.ATOM
_user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
_user32.CreateWindowExW.restype = wintypes.HWND
_user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.DefWindowProcW.restype = _LRESULT
_user32.DestroyWindow.argtypes = [wintypes.HWND]
_user32.DestroyWindow.restype = wintypes.BOOL
_user32.PeekMessageW.argtypes = [
    ctypes.POINTER(_MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.UINT,
]
_user32.PeekMessageW.restype = wintypes.BOOL
_user32.TranslateMessage.argtypes = [ctypes.POINTER(_MSG)]
_user32.TranslateMessage.restype = wintypes.BOOL
_user32.DispatchMessageW.argtypes = [ctypes.POINTER(_MSG)]
_user32.DispatchMessageW.restype = _LRESULT
_user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.PostMessageW.restype = wintypes.BOOL
_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE
_wtsapi.WTSRegisterSessionNotification.argtypes = [wintypes.HWND, wintypes.DWORD]
_wtsapi.WTSRegisterSessionNotification.restype = wintypes.BOOL
_wtsapi.WTSUnRegisterSessionNotification.argtypes = [wintypes.HWND]
_wtsapi.WTSUnRegisterSessionNotification.restype = wintypes.BOOL


def probe_locked() -> bool | None:
    """True when the interactive desktop is the lock screen.

    OpenInputDesktop fails with access denied while Windows is locked because
    the input desktop is Winlogon. A successful open means the session is in use.
    On some Windows 11 builds that open succeeds again while the lock screen is
    still up, so a lock is kept until Windows sends a session-unlock notice.
    """
    desktop = _user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
    if desktop:
        _user32.CloseDesktop(desktop)
        return False
    if ctypes.get_last_error() == ERROR_ACCESS_DENIED:
        return True
    return None


class SessionMonitor:
    def __init__(self) -> None:
        self._cached = False
        self._optimistic_until = 0.0
        self._events_ready = False
        self._guard = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._hwnd: wintypes.HWND | int = 0
        self._wndproc = _WNDPROC(self._on_message)
        self._class_name = f"AFKSessionMonitor.{id(self)}"

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        initial = probe_locked()
        if initial is not None:
            self._cached = initial
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="afk-session", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        hwnd = self._hwnd
        if hwnd:
            _user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def is_locked(self) -> bool:
        with self._guard:
            return self._cached

    def lock(self) -> bool:
        ok = bool(_user32.LockWorkStation())
        if ok:
            self._mark(True, "lock request")
            with self._guard:
                self._optimistic_until = time.monotonic() + 1.5
        return ok

    def _loop(self) -> None:
        hwnd = self._create_window()
        self._hwnd = hwnd or 0
        if hwnd:
            self._events_ready = bool(
                _wtsapi.WTSRegisterSessionNotification(hwnd, NOTIFY_FOR_THIS_SESSION)
            )
            if not self._events_ready:
                logging.getLogger("afk").warning("session lock notices are unavailable")
        try:
            while not self._stop.is_set():
                self._drain_messages()
                if self._stop.is_set():
                    break
                self._apply_probe()
                self._stop.wait(0.4)
        finally:
            if hwnd:
                if self._events_ready:
                    _wtsapi.WTSUnRegisterSessionNotification(hwnd)
                _user32.DestroyWindow(hwnd)
            self._hwnd = 0
            self._events_ready = False

    def _apply_probe(self) -> None:
        probed = probe_locked()
        if probed is True:
            self._mark(True, "desktop")
            return
        if probed is False and not self._events_ready:
            with self._guard:
                if time.monotonic() < self._optimistic_until or not self._cached:
                    return
            self._mark(False, "desktop")

    def _create_window(self) -> wintypes.HWND | None:
        window_class = _WNDCLASSW()
        window_class.lpfnWndProc = self._wndproc
        window_class.hInstance = _kernel32.GetModuleHandleW(None)
        window_class.lpszClassName = self._class_name
        atom = _user32.RegisterClassW(ctypes.byref(window_class))
        if not atom and ctypes.get_last_error() != ERROR_CLASS_ALREADY_EXISTS:
            logging.getLogger("afk").warning("session window could not be registered")
            return None
        hwnd = _user32.CreateWindowExW(
            0,
            self._class_name,
            "AFK",
            0,
            0,
            0,
            0,
            0,
            HWND_MESSAGE,
            None,
            window_class.hInstance,
            None,
        )
        if not hwnd:
            logging.getLogger("afk").warning("session window could not be created")
            return None
        return hwnd

    def _drain_messages(self) -> None:
        msg = _MSG()
        while _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
            if msg.message == WM_CLOSE:
                self._stop.set()
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

    def _on_message(self, hwnd, message, wparam, lparam):
        if message == WM_WTSSESSION_CHANGE:
            event = int(wparam)
            if event == WTS_SESSION_LOCK:
                self._mark(True, "windows")
            elif event == WTS_SESSION_UNLOCK:
                self._mark(False, "windows")
            return 0
        return _user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _mark(self, locked: bool, reason: str) -> None:
        with self._guard:
            changed = locked != self._cached
            self._cached = locked
            if locked:
                self._optimistic_until = 0.0
        if changed:
            logging.getLogger("afk").info(
                "session %s (%s)", "locked" if locked else "unlocked", reason
            )
