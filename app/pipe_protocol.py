"""Local pipe messages shared with the credential provider.

Layout (little-endian, no padding). The C++ side in
credential_provider/src/protocol.h must stay in sync.

Challenge (provider -> app), 40 bytes:
    uint32 magic = 0x41464B31
    uint32 type = 1
    uint8 nonce[32]

Unlock (app -> provider):
    uint32 magic
    uint32 type = 2
    uint8 nonce[32]
    uint32 user_byte_len
    utf-16-le user bytes
    uint32 domain_byte_len
    utf-16-le domain bytes
    uint32 password_byte_len
    utf-16-le password bytes

Result (provider -> app), 12 bytes:
    uint32 magic
    uint32 type = 3
    uint32 code   0 = accepted, 1 = rejected
"""

from __future__ import annotations

import struct

MAGIC = 0x41464B31
TYPE_CHALLENGE = 1
TYPE_UNLOCK = 2
TYPE_RESULT = 3
NONCE_LEN = 32
MAX_UTF16_BYTES = 512

PIPE_NAME = r"\\.\pipe\AFKPresenceLock"


def parse_challenge(message: bytes) -> bytes:
    if len(message) != 8 + NONCE_LEN:
        raise ValueError("bad challenge")
    magic, kind = struct.unpack_from("<II", message, 0)
    if magic != MAGIC or kind != TYPE_CHALLENGE:
        raise ValueError("bad challenge")
    return message[8 : 8 + NONCE_LEN]


def build_unlock(
    nonce: bytes,
    username: str,
    domain: str,
    password_utf16: bytes,
) -> bytearray:
    if len(nonce) != NONCE_LEN:
        raise ValueError("bad nonce")
    user = _utf16(username)
    dom = _utf16(domain)
    if not password_utf16 or len(password_utf16) > MAX_UTF16_BYTES or len(password_utf16) % 2:
        raise ValueError("bad password")
    message = bytearray()
    message += struct.pack("<II", MAGIC, TYPE_UNLOCK)
    message += nonce
    for part in (user, dom, password_utf16):
        message += struct.pack("<I", len(part))
        message += part
    return message


def parse_result(message: bytes) -> int:
    if len(message) != 12:
        raise ValueError("bad result")
    magic, kind, code = struct.unpack("<III", message)
    if magic != MAGIC or kind != TYPE_RESULT:
        raise ValueError("bad result")
    return code


def _utf16(value: str) -> bytes:
    raw = value.encode("utf-16-le")
    if len(raw) > MAX_UTF16_BYTES:
        raise ValueError("value too long")
    return raw
