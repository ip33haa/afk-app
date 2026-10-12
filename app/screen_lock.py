"""Full-screen lock the app can dismiss when the enrolled face returns.

Windows will not unlock its own lock screen without an administrator-registered
sign-in component. This screen covers the desktop until the face matches or the
saved PIN is entered.
"""

from __future__ import annotations

import ctypes
import logging
import os
import threading
import tkinter as tk
from ctypes import wintypes
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageTk

from app.anime import random_anime_line
from app.wallpaper import lock_image_path

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
_kernel32.GetTimeFormatEx.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.LPCWSTR,
    wintypes.LPWSTR,
    ctypes.c_int,
]
_kernel32.GetTimeFormatEx.restype = ctypes.c_int
_kernel32.GetDateFormatEx.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.LPCWSTR,
    wintypes.LPWSTR,
    ctypes.c_int,
    wintypes.LPCWSTR,
]
_kernel32.GetDateFormatEx.restype = ctypes.c_int

_TIME_NOSECONDS = 0x00000002


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
        self._message = random_anime_line()
        self._window: tk.Toplevel | None = None
        self._status: tk.Label | None = None
        self._pin: tk.StringVar | None = None
        self._error: tk.Label | None = None
        self._after: str | None = None
        self._clock_after: str | None = None
        self._hook: wintypes.HHOOK | int = 0
        self._hookproc = _HOOKPROC(self._on_key)
        self._image_label: tk.Label | None = None
        self._signin: tk.Frame | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._background: Image.Image | None = None
        self._fonts: dict[str, ImageFont.ImageFont] = {}

    def is_locked(self) -> bool:
        return self._locked

    @property
    def message(self) -> str:
        return self._message

    def lock(self, message: str = "") -> None:
        if not self._locked:
            self._message = message or random_anime_line()
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
        window.bind("<Button-1>", self._reveal_signin)
        window.attributes("-topmost", True)
        self._window = window
        self._image_label = tk.Label(window, borderwidth=0, bg="black")
        self._image_label.place(x=0, y=0, relwidth=1, relheight=1)
        self._image_label.bind("<Button-1>", self._reveal_signin)
        self._status = None
        self._signin = tk.Frame(window, bg="#1c1c1c")
        tk.Label(self._signin, text="PIN", fg="white", bg="#1c1c1c", font=("Segoe UI", 12)).pack(side="left", padx=(16, 8), pady=12)
        self._pin = tk.StringVar()
        entry = tk.Entry(self._signin, textvariable=self._pin, show="*", font=("Segoe UI", 16), width=22, bg="#2a2a2a", fg="white", insertbackground="white", relief="flat")
        entry.pack(side="left", padx=(0, 8), pady=12)
        entry.bind("<Return>", self._submit_pin)
        tk.Button(self._signin, text="Unlock", command=self._submit_pin).pack(side="left", padx=(0, 16))
        self._error = tk.Label(self._signin, text="", fg="#ffb4b4", bg="#1c1c1c", font=("Segoe UI", 11))
        self._error.pack(side="left", padx=(0, 12))
        self._place(window)
        self._prepare_background(window)
        self._render()
        self._install_hook()
        self._clip()
        self._raise()
        self._keep()
        self._tick_clock()

    def _hide(self) -> None:
        self._release_input()
        window = self._window
        self._window = None
        self._status = None
        self._pin = None
        self._error = None
        self._image_label = None
        self._signin = None
        self._photo = None
        self._background = None
        if self._after is not None and window is not None:
            try:
                window.after_cancel(self._after)
            except tk.TclError:
                pass
        if self._clock_after is not None and window is not None:
            try:
                window.after_cancel(self._clock_after)
            except tk.TclError:
                pass
        self._after = None
        self._clock_after = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

    def _apply_message(self) -> None:
        if self._window is not None:
            self._render()

    def _reveal_signin(self, _event=None) -> None:
        signin = self._signin
        if signin is None or not self._locked:
            return
        signin.place(relx=0.5, rely=0.94, anchor="s")
        for child in signin.winfo_children():
            if isinstance(child, tk.Entry):
                child.focus_set()
                break

    def _prepare_background(self, window: tk.Toplevel) -> None:
        window.update_idletasks()
        width = window.winfo_width()
        height = window.winfo_height()
        if width < 100 or height < 100:
            width = max(self._root.winfo_vrootwidth(), 1)
            height = max(self._root.winfo_vrootheight(), 1)
        image = _open_wallpaper()
        if image is None:
            self._background = Image.new("RGB", (width, height), (18, 28, 42))
            return
        self._background = _cover(image.convert("RGB"), width, height)

    def _render(self) -> None:
        background = self._background
        label = self._image_label
        if background is None or label is None:
            return
        frame = background.copy()
        draw = ImageDraw.Draw(frame)
        width, height = frame.size
        center_x, center_y = _primary_center(self._root, width, height)
        clock_size = max(64, int(height * 0.11))
        date_size = max(18, int(height * 0.028))
        caption_size = max(14, int(height * 0.018))
        _shadow_text(draw, (center_x, center_y), _windows_time(), self._font(clock_size, light=True))
        _shadow_text(draw, (center_x, center_y + int(height * 0.075)), _windows_date(), self._font(date_size, light=False))
        _caption(draw, center_x, center_y + int(height * 0.13), self._message, self._font(caption_size, light=False), width)
        self._photo = ImageTk.PhotoImage(frame)
        label.configure(image=self._photo)

    def _font(self, size: int, *, light: bool) -> ImageFont.ImageFont:
        key = f"{'light' if light else 'regular'}-{size}"
        cached = self._fonts.get(key)
        if cached is not None:
            return cached
        windir = os.environ.get("WINDIR", r"C:\Windows")
        names = ("segoeuil.ttf", "segoeui.ttf") if light else ("segoeui.ttf", "segoeuil.ttf")
        font: ImageFont.ImageFont
        try:
            font = ImageFont.truetype(_font_file(windir, names), size)
        except OSError:
            font = ImageFont.load_default()
        self._fonts[key] = font
        return font

    def _tick_clock(self) -> None:
        if not self._locked or self._window is None:
            return
        self._render()
        self._clock_after = self._window.after(1000, self._tick_clock)

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
            if int(wparam) in (WM_KEYDOWN, WM_SYSKEYDOWN):
                self._root.after(0, self._reveal_signin)
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


def _font_file(windir: str, names: tuple[str, ...]) -> str:
    fonts = os.path.join(windir, "Fonts")
    for name in names:
        path = os.path.join(fonts, name)
        if os.path.isfile(path):
            return path
    raise OSError("Segoe UI is not installed")


def _open_wallpaper() -> Image.Image | None:
    path = lock_image_path()
    if path is None:
        return None
    try:
        with Image.open(path) as image:
            return image.convert("RGB")
    except OSError:
        logging.getLogger("afk").info("wallpaper could not be opened")
        return None


def _cover(image: Image.Image, width: int, height: int) -> Image.Image:
    scale = max(width / image.width, height / image.height)
    resized = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.Resampling.LANCZOS)
    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def _primary_center(root: tk.Tk, width: int, height: int) -> tuple[int, int]:
    origin_x = root.winfo_vrootx()
    origin_y = root.winfo_vrooty()
    primary_w = max(root.winfo_screenwidth(), 1)
    primary_h = max(root.winfo_screenheight(), 1)
    center_x = min(width - 1, max(0, -origin_x + primary_w // 2))
    center_y = min(height - 1, max(0, -origin_y + int(primary_h * 0.40)))
    return center_x, center_y


def _shadow_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font: ImageFont.ImageFont) -> None:
    x, y = xy
    draw.text((x + 2, y + 3), text, font=font, fill=(0, 0, 0), anchor="mm")
    draw.text((x, y), text, font=font, fill=(255, 255, 255), anchor="mm")


def _caption(draw: ImageDraw.ImageDraw, center_x: int, top: int, text: str, font: ImageFont.ImageFont, width: int) -> None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return
    line_height = max(18, int(getattr(font, "size", 18) * 1.35))
    for index, line in enumerate(lines[:4]):
        _shadow_text(draw, (center_x, top + index * line_height), _fit_line(line, font, int(width * 0.7)), font)


def _fit_line(text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    if font.getlength(text) <= max_width:
        return text
    words = text.split()
    kept: list[str] = []
    for word in words:
        trial = " ".join([*kept, word])
        if font.getlength(trial) > max_width:
            break
        kept.append(word)
    return " ".join(kept) if kept else text


def _windows_time() -> str:
    buffer = ctypes.create_unicode_buffer(80)
    if _kernel32.GetTimeFormatEx(None, _TIME_NOSECONDS, None, None, buffer, 80):
        return buffer.value
    return datetime.now().strftime("%H:%M")


def _windows_date() -> str:
    buffer = ctypes.create_unicode_buffer(80)
    if _kernel32.GetDateFormatEx(None, 0, None, "dddd, MMMM d", buffer, 80, None):
        return buffer.value
    return datetime.now().strftime("%A, %B %#d")

