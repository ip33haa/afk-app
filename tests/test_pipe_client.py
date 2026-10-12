"""The unlock client against a local stand-in for the credential provider."""

import ctypes
import struct
import tempfile
import threading
import unittest
from ctypes import wintypes
from pathlib import Path

from app.pipe_protocol import MAGIC, PIPE_NAME, TYPE_CHALLENGE, TYPE_RESULT, TYPE_UNLOCK
from app.secure_store import SecureStore, wipe
from app.unlock_client import UnlockClient

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateNamedPipeW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
]
_kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
_kernel32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
_kernel32.ConnectNamedPipe.restype = wintypes.BOOL
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
_kernel32.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
_kernel32.DisconnectNamedPipe.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL

_PIPE_ACCESS_DUPLEX = 0x3
_PIPE_TYPE_MESSAGE = 0x4
_PIPE_READMODE_MESSAGE = 0x2
_ERROR_PIPE_CONNECTED = 535


class PipeClientTests(unittest.TestCase):
    def test_client_submits_the_saved_password_once(self):
        seen = {}
        ready = threading.Event()
        finished = threading.Event()

        def serve():
            pipe = _kernel32.CreateNamedPipeW(
                PIPE_NAME,
                _PIPE_ACCESS_DUPLEX,
                _PIPE_TYPE_MESSAGE | _PIPE_READMODE_MESSAGE,
                1,
                4096,
                4096,
                0,
                None,
            )
            ready.set()
            try:
                connected = _kernel32.ConnectNamedPipe(pipe, None)
                if not connected and ctypes.get_last_error() != _ERROR_PIPE_CONNECTED:
                    return
                nonce = bytes(range(32))
                challenge = struct.pack("<II", MAGIC, TYPE_CHALLENGE) + nonce
                written = wintypes.DWORD()
                _kernel32.WriteFile(pipe, challenge, len(challenge), ctypes.byref(written), None)
                raw = ctypes.create_string_buffer(4096)
                read = wintypes.DWORD()
                if not _kernel32.ReadFile(pipe, raw, len(raw), ctypes.byref(read), None):
                    return
                message = raw.raw[: read.value]
                seen["nonce"] = message[8:40]
                seen["type"] = struct.unpack_from("<I", message, 4)[0]
                offset = 40
                user_len = struct.unpack_from("<I", message, offset)[0]
                offset += 4 + user_len
                domain_len = struct.unpack_from("<I", message, offset)[0]
                offset += 4 + domain_len
                password_len = struct.unpack_from("<I", message, offset)[0]
                offset += 4
                seen["password"] = bytes(message[offset : offset + password_len])
                result = struct.pack("<III", MAGIC, TYPE_RESULT, 0)
                _kernel32.WriteFile(pipe, result, len(result), ctypes.byref(written), None)
            finally:
                _kernel32.DisconnectNamedPipe(pipe)
                _kernel32.CloseHandle(pipe)
                finished.set()

        thread = threading.Thread(target=serve)
        thread.start()
        self.assertTrue(ready.wait(2))
        password = None
        try:
            with tempfile.TemporaryDirectory() as folder:
                store = SecureStore(Path(folder), logon=lambda user, domain, secret: secret == "correct-horse")
                store.save("correct-horse")
                outcome = UnlockClient(store).try_unlock()
                self.assertEqual(outcome, "accepted")
        finally:
            thread.join(timeout=3)
            finished.wait(1)
            if "password" in seen:
                wipe(bytearray(seen["password"]))

        self.assertEqual(seen.get("type"), TYPE_UNLOCK)
        self.assertEqual(seen.get("nonce"), bytes(range(32)))
        self.assertEqual(seen.get("password"), "correct-horse".encode("utf-16-le"))


if __name__ == "__main__":
    unittest.main()
