"""Full-screen lock the app can dismiss when the enrolled face returns.

Windows will not unlock its own lock screen without an administrator-registered
sign-in component. This screen covers the desktop until the face matches or the
saved PIN is entered.
"""

from __future__ import annotations

import ctypes
import logging
import threading
import tkinter as tk
from ctypes import wintypes

from app.verses import random_verse

WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
VK_TAB = 0x09
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_APPS = 0x5D
VK_F4 = 0x73
VK_MENU = 0x12
VK_CONTROL = 0x11
HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040

_LRESULT = ctypes.c_ssize_t
_HOOKPROC = ctypes.WINFUNCTYPE(_LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
_user32.SetWindowsHookExW.restype = wintypes.HHOOK
_user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
_user32.UnhookWindowsHookEx.restype = wintypes.BOOL
_user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
_user32.CallNextHookEx.restype = _LRESULT
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetAsyncKeyState.restype = wintypes.SHORT
_user32.ClipCursor.argtypes = [ctypes.POINTER(_RECT)]
_user32.ClipCursor.restype = wintypes.BOOL
_user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
_user32.SetWindowPos.restype = wintypes.BOOL
_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE


def block_lock_key(vk: int, *, alt: bool, ctrl: bool) -> bool:
    """Swallow keys that would leave the lock screen. Typing a PIN still works."""
    if vk in (VK_LWIN, VK_RWIN, VK_APPS):
        return True
    if alt and vk in (VK_TAB, VK_ESCAPE, VK_F4, VK_SPACE):
        return True
    if ctrl and vk == VK_ESCAPE:
        return True
    return False


class ScreenLock:
    def __init__(self, root: tk.Tk, store) -> None:
        self._root = root
        self._store = store
        self._locked = False
        self._message = random_verse()
        self._window: tk.Toplevel | None = None
        self._status: tk.Label | None = None
        self._pin: tk.StringVar | None = None
        self._error: tk.Label | None = None
        self._after: str | None = None
        self._hook: wintypes.HHOOK | int = 0
        self._hookproc = _HOOKPROC(self._on_key)

    def is_locked(self) -> bool:
        return self._locked

    @property
    def message(self) -> str:
        return self._message

    def lock(self, message: str = "") -> None:
        del message
        if not self._locked:
            self._message = random_verse()
        self._locked = True
        self._on_ui(self._show)

    def unlock(self) -> None:
        self._locked = False
        self._release_input()
        self._on_ui(self._hide)

    def set_message(self, message: str) -> None:
        if not message or message == self._message:
            return
        self._message = message
        self._on_ui(self._apply_message)

    def _on_ui(self, action) -> None:
        if threading.current_thread() is threading.main_thread():
            action()
            return
        try:
            self._root.after(0, action)
        except tk.TclError:
            pass

    def _show(self) -> None:
        if not self._locked:
            return
        if self._window is not None:
            self._apply_message()
            self._raise()
            return
        window = tk.Toplevel(self._root)
        window.overrideredirect(True)
        window.configure(bg="black")
        window.protocol("WM_DELETE_WINDOW", lambda: None)
        window.bind("<Alt-F4>", lambda _event: "break")
        window.attributes("-topmost", True)
        self._window = window
        self._status = tk.Label(
            window,
            text=self._message,
            fg="white",
            bg="black",
            font=("Segoe UI", 22),
            wraplength=860,
            justify="center",
        )
        self._status.pack(expand=True)
        form = tk.Frame(window, bg="black")
        form.pack(side="bottom", pady=48)
        tk.Label(form, text="PIN", fg="white", bg="black", font=("Segoe UI", 12)).pack(side="left")
        self._pin = tk.StringVar()
        entry = tk.Entry(form, textvariable=self._pin, show="*", font=("Segoe UI", 14), width=24)
        entry.pack(side="left", padx=8)
        entry.bind("<Return>", self._submit_pin)
        tk.Button(form, text="Unlock", command=self._submit_pin).pack(side="left")
        self._error = tk.Label(window, text="", fg="#e07070", bg="black", font=("Segoe UI", 11))
        self._error.pack(side="bottom", pady=(0, 12))
        tk.Label(
            window,
            text="If the camera cannot see you, enter your PIN.",
            fg="#bbbbbb",
            bg="black",
            font=("Segoe UI", 11),
        ).pack(side="bottom")
        self._place(window)
        self._install_hook()
        self._clip()
        self._raise()
        entry.focus_set()
        self._keep()

    def _hide(self) -> None:
        self._release_input()
        window = self._window
        self._window = None
        self._status = None
        self._pin = None
        self._error = None
        if self._after is not None and window is not None:
            try:
                window.after_cancel(self._after)
            except tk.TclError:
                pass
        self._after = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

    def _apply_message(self) -> None:
        if self._status is not None:
            self._status.configure(text=self._message)

    def _place(self, window: tk.Toplevel) -> None:
        self._root.update_idletasks()
        x = self._root.winfo_vrootx()
        y = self._root.winfo_vrooty()
        width = self._root.winfo_vrootwidth()
        height = self._root.winfo_vrootheight()
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _raise(self) -> None:
        window = self._window
        if window is None or not self._locked:
            return
        try:
            window.lift()
            window.attributes("-topmost", True)
            hwnd = window.winfo_id()
            _user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        except tk.TclError:
            pass

    def _keep(self) -> None:
        if not self._locked or self._window is None:
            return
        self._raise()
        self._after = self._window.after(400, self._keep)

    def _clip(self) -> None:
        window = self._window
        if window is None:
            return
        try:
            window.update_idletasks()
            rect = _RECT(window.winfo_rootx(), window.winfo_rooty(), window.winfo_rootx() + window.winfo_width(), window.winfo_rooty() + window.winfo_height())
            _user32.ClipCursor(ctypes.byref(rect))
        except tk.TclError:
            pass

    def _install_hook(self) -> None:
        if self._hook:
            return
        handle = _user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._hookproc,
            _kernel32.GetModuleHandleW(None),
            0,
        )
        self._hook = handle or 0
        if not self._hook:
            logging.getLogger("afk").warning("lock screen could not block shortcut keys")

    def _release_input(self) -> None:
        hook = self._hook
        self._hook = 0
        if hook:
            _user32.UnhookWindowsHookEx(hook)
        _user32.ClipCursor(None)

    def _on_key(self, code, wparam, lparam):
        if code == HC_ACTION and self._locked and int(wparam) in (WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP):
            info = ctypes.cast(lparam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            alt = bool(_user32.GetAsyncKeyState(VK_MENU) & 0x8000)
            ctrl = bool(_user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
            if block_lock_key(int(info.vkCode), alt=alt, ctrl=ctrl):
                return 1
        return _user32.CallNextHookEx(self._hook or None, code, wparam, lparam)

    def _submit_pin(self, _event=None) -> None:
        pin = self._pin.get() if self._pin is not None else ""
        if self._store.pin_matches(pin):
            if self._pin is not None:
                self._pin.set("")
            self.unlock()
            return
        if self._pin is not None:
            self._pin.set("")
        if self._error is not None:
            self._error.configure(text="That PIN was not accepted")
