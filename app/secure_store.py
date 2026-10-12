"""Encrypt the Windows password with DPAPI for the current user only."""

from __future__ import annotations

import ctypes
import hmac
import os
import struct
from ctypes import wintypes

from app.paths import data_dir

_MAGIC = b"AFK1"
_VERSION = 1
_ENTROPY = b"AFK-Camera-Lock-v1"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01
_LOGON32_LOGON_INTERACTIVE = 2
_LOGON32_PROVIDER_DEFAULT = 0
_NameSamCompatible = 2
_NameUserPrincipal = 8

_crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
_secur32 = ctypes.WinDLL("secur32", use_last_error=True)


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


_crypt32.CryptProtectData.argtypes = [
    ctypes.POINTER(DATA_BLOB),
    wintypes.LPCWSTR,
    ctypes.POINTER(DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(DATA_BLOB),
]
_crypt32.CryptProtectData.restype = wintypes.BOOL
_crypt32.CryptUnprotectData.argtypes = [
    ctypes.POINTER(DATA_BLOB),
    ctypes.POINTER(wintypes.LPWSTR),
    ctypes.POINTER(DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(DATA_BLOB),
]
_crypt32.CryptUnprotectData.restype = wintypes.BOOL
_kernel32.LocalFree.argtypes = [ctypes.c_void_p]
_kernel32.LocalFree.restype = ctypes.c_void_p
_advapi32.LogonUserW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.HANDLE),
]
_advapi32.LogonUserW.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL
_secur32.GetUserNameExW.argtypes = [wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.ULONG)]
_secur32.GetUserNameExW.restype = wintypes.BOOL


def wipe(buffer: bytearray | None) -> None:
    if not buffer:
        return
    size = len(buffer)
    if size:
        ctypes.memset((ctypes.c_char * size).from_buffer(buffer), 0, size)
    buffer.clear()


def pack_secret(username: str, domain: str, password: str) -> bytes:
    user = username.encode("utf-8")
    dom = domain.encode("utf-8")
    secret = password.encode("utf-16-le")
    if not secret:
        raise ValueError("Enter your Windows account password, not a PIN.")
    return b"".join(
        [
            _MAGIC,
            struct.pack("<I", _VERSION),
            struct.pack("<I", len(user)),
            user,
            struct.pack("<I", len(dom)),
            dom,
            struct.pack("<I", len(secret)),
            secret,
        ]
    )


def unpack_secret(payload: bytes) -> tuple[str, str, bytearray]:
    if len(payload) < 16 or payload[:4] != _MAGIC:
        raise ValueError("saved sign-in data is unreadable")
    version = struct.unpack_from("<I", payload, 4)[0]
    if version != _VERSION:
        raise ValueError("saved sign-in data is unreadable")
    offset = 8
    user, offset = _take(payload, offset)
    domain, offset = _take(payload, offset)
    password, offset = _take(payload, offset)
    if offset != len(payload) or not password:
        raise ValueError("saved sign-in data is unreadable")
    return user.decode("utf-8"), domain.decode("utf-8"), bytearray(password)


class SecureStore:
    def __init__(self, directory=None, logon=None) -> None:
        self._directory = directory or data_dir()
        self._directory.mkdir(parents=True, exist_ok=True)
        self._logon = logon or windows_logon_ok

    def has_secret(self) -> bool:
        return (self._directory / "secret.bin").exists()

    def save(self, password: str) -> None:
        if not password:
            raise ValueError("Enter your Windows account password, not a PIN.")
        ok, username, domain = verify_password(password, logon=self._logon)
        if not ok:
            raise ValueError(
                "Windows did not accept that PIN. If you sign in with Windows Hello, enter your account password instead."
            )
        protected = protect(pack_secret(username, domain, password))
        (self._directory / "secret.bin").write_bytes(protected)

    def load(self) -> tuple[str, str, bytearray]:
        blob = (self._directory / "secret.bin").read_bytes()
        return unpack_secret(unprotect(blob))

    def pin_matches(self, pin: str) -> bool:
        """True when pin is the saved sign-in secret. The pin is never logged."""
        if not pin or not self.has_secret():
            return False
        saved = None
        entered = None
        try:
            _user, _domain, saved = self.load()
            entered = bytearray(pin.encode("utf-16-le"))
            if len(entered) != len(saved):
                return False
            return hmac.compare_digest(entered, saved)
        except (OSError, ValueError):
            return False
        finally:
            wipe(saved)
            wipe(entered)

    def clear(self) -> None:
        for name in ("secret.bin", "face.npy"):
            path = self._directory / name
            if path.exists():
                path.unlink()


def current_account_label() -> str:
    username, domain = _sam_account()
    if domain and domain not in (".", username):
        return f"{domain}\\{username}"
    return username or "this account"


def verify_password(password: str, logon=None) -> tuple[bool, str, str]:
    """Return the username and domain that Windows accepted."""
    check = logon or windows_logon_ok
    username, domain = _sam_account()
    candidates = [(username, domain), (username, ".")]
    upn = _user_principal()
    if upn:
        candidates.append((upn, "MicrosoftAccount"))
    seen = set()
    for user, dom in candidates:
        key = (user, dom)
        if not user or key in seen:
            continue
        seen.add(key)
        if check(user, dom, password):
            return True, user, dom
    return False, username, domain


def windows_logon_ok(username: str, domain: str, password: str) -> bool:
    token = wintypes.HANDLE()
    domain_arg = None if domain in ("", ".") else domain
    ok = _advapi32.LogonUserW(
        username,
        domain_arg,
        password,
        _LOGON32_LOGON_INTERACTIVE,
        _LOGON32_PROVIDER_DEFAULT,
        ctypes.byref(token),
    )
    if ok:
        _kernel32.CloseHandle(token)
        return True
    return False


def protect(data: bytes) -> bytes:
    incoming, incoming_buf = _blob(data)
    entropy, entropy_buf = _blob(_ENTROPY)
    outgoing = DATA_BLOB()
    ok = _crypt32.CryptProtectData(
        ctypes.byref(incoming),
        "AFK",
        ctypes.byref(entropy),
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(outgoing),
    )
    del incoming_buf, entropy_buf
    if not ok:
        raise OSError(ctypes.get_last_error())
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        _kernel32.LocalFree(outgoing.pbData)


def unprotect(data: bytes) -> bytes:
    incoming, incoming_buf = _blob(data)
    entropy, entropy_buf = _blob(_ENTROPY)
    outgoing = DATA_BLOB()
    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(incoming),
        None,
        ctypes.byref(entropy),
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(outgoing),
    )
    del incoming_buf, entropy_buf
    if not ok:
        raise OSError(ctypes.get_last_error())
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        _kernel32.LocalFree(outgoing.pbData)


def _blob(data: bytes) -> tuple[DATA_BLOB, ctypes.Array]:
    holder = ctypes.create_string_buffer(data)
    blob = DATA_BLOB()
    blob.cbData = len(data)
    blob.pbData = ctypes.cast(holder, ctypes.POINTER(ctypes.c_byte))
    return blob, holder


def _take(payload: bytes, offset: int) -> tuple[bytes, int]:
    if offset + 4 > len(payload):
        raise ValueError("saved sign-in data is unreadable")
    size = struct.unpack_from("<I", payload, offset)[0]
    offset += 4
    if size > 4096 or offset + size > len(payload):
        raise ValueError("saved sign-in data is unreadable")
    return payload[offset : offset + size], offset + size


def _sam_account() -> tuple[str, str]:
    name = _name_ex(_NameSamCompatible)
    if name and "\\" in name:
        domain, user = name.split("\\", 1)
        return user, domain
    user = os.environ.get("USERNAME") or ""
    domain = os.environ.get("USERDOMAIN") or "."
    return user, domain


def _user_principal() -> str:
    return _name_ex(_NameUserPrincipal)


def _name_ex(kind: int) -> str:
    size = wintypes.ULONG(256)
    buf = ctypes.create_unicode_buffer(256)
    if _secur32.GetUserNameExW(kind, buf, ctypes.byref(size)):
        return buf.value
    if ctypes.get_last_error() == 122:  # ERROR_INSUFFICIENT_BUFFER
        buf = ctypes.create_unicode_buffer(size.value)
        if _secur32.GetUserNameExW(kind, buf, ctypes.byref(size)):
            return buf.value
    return ""
