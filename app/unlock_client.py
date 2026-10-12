"""Send a face-match unlock to the lock-screen credential provider."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from app.logging_setup import setup
from app.pipe_protocol import PIPE_NAME, build_unlock, parse_challenge, parse_result
from app.secure_store import SecureStore, wipe

_ERROR_FILE_NOT_FOUND = 2
_ERROR_PIPE_BUSY = 231
_ERROR_IO_PENDING = 997
_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_OPEN_EXISTING = 3
_FILE_FLAG_OVERLAPPED = 0x40000000
_PIPE_READMODE_MESSAGE = 2
_INVALID_HANDLES = {0, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF}

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]
_kernel32.CreateFileW.restype = wintypes.HANDLE
_kernel32.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
_kernel32.WaitNamedPipeW.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL
_kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateEventW.restype = wintypes.HANDLE
_kernel32.ReadFile.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]
_kernel32.ReadFile.restype = wintypes.BOOL
_kernel32.WriteFile.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]
_kernel32.WriteFile.restype = wintypes.BOOL
_kernel32.GetOverlappedResult.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.BOOL,
]
_kernel32.GetOverlappedResult.restype = wintypes.BOOL
_kernel32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
_kernel32.CancelIoEx.restype = wintypes.BOOL
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_kernel32.SetNamedPipeHandleState.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD),
]
_kernel32.SetNamedPipeHandleState.restype = wintypes.BOOL


class OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_void_p),
        ("InternalHigh", ctypes.c_void_p),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]


class UnlockClient:
    def __init__(self, store: SecureStore | None = None) -> None:
        self._store = store or SecureStore()
        self._log = setup()

    def try_unlock(self) -> str:
        """Return accepted, rejected, or unavailable. The password is wiped either way."""
        try:
            username, domain, password = self._store.load()
        except (OSError, ValueError):
            self._log.info("saved sign-in data could not be read")
            return "rejected"
        message = None
        handle = None
        try:
            handle = _open_pipe()
            if handle is None:
                return "unavailable"
            nonce = parse_challenge(_read_message(handle))
            message = build_unlock(nonce, username, domain, password)
            _write_message(handle, message)
            code = parse_result(_read_message(handle))
            return "accepted" if code == 0 else "rejected"
        except (OSError, TimeoutError, ValueError):
            self._log.info("unlock pipe was not ready")
            return "unavailable"
        finally:
            wipe(password)
            if message is not None:
                wipe(message)
            if handle is not None:
                _kernel32.CloseHandle(handle)


def _open_pipe():
    _kernel32.WaitNamedPipeW(PIPE_NAME, 400)
    handle = _kernel32.CreateFileW(
        PIPE_NAME,
        _GENERIC_READ | _GENERIC_WRITE,
        0,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_OVERLAPPED,
        None,
    )
    if not _handle_ok(handle):
        return None
    mode = wintypes.DWORD(_PIPE_READMODE_MESSAGE)
    _kernel32.SetNamedPipeHandleState(handle, ctypes.byref(mode), None, None)
    return handle


def _handle_ok(handle) -> bool:
    if not handle:
        return False
    try:
        value = int(handle)
    except (TypeError, ValueError):
        return False
    return value not in _INVALID_HANDLES


def _read_message(handle, timeout_ms: int = 3000) -> bytes:
    raw = ctypes.create_string_buffer(4096)
    return _io(handle, raw, len(raw), timeout_ms, write=False)


def _write_message(handle, payload: bytearray, timeout_ms: int = 3000) -> None:
    raw = (ctypes.c_char * len(payload)).from_buffer(payload)
    _io(handle, raw, len(payload), timeout_ms, write=True)


def _io(handle, buffer, size: int, timeout_ms: int, write: bool) -> bytes:
    done = wintypes.DWORD(0)
    overlapped = OVERLAPPED()
    overlapped.hEvent = _kernel32.CreateEventW(None, True, False, None)
    if not overlapped.hEvent:
        raise OSError(ctypes.get_last_error())
    try:
        call = _kernel32.WriteFile if write else _kernel32.ReadFile
        ok = call(handle, buffer, size, ctypes.byref(done), ctypes.byref(overlapped))
        if not ok:
            err = ctypes.get_last_error()
            if err != _ERROR_IO_PENDING:
                raise OSError(err)
            waited = _kernel32.WaitForSingleObject(overlapped.hEvent, timeout_ms)
            if waited != 0:
                _kernel32.CancelIoEx(handle, ctypes.byref(overlapped))
                raise TimeoutError()
            if not _kernel32.GetOverlappedResult(handle, ctypes.byref(overlapped), ctypes.byref(done), False):
                raise OSError(ctypes.get_last_error())
        if write:
            return b""
        return buffer.raw[: done.value]
    finally:
        _kernel32.CloseHandle(overlapped.hEvent)
