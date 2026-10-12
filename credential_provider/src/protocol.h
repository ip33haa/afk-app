#pragma once

#include <cstdint>

// Keep this layout identical to app/pipe_protocol.py.
constexpr uint32_t AFK_MAGIC = 0x41464B31u;
constexpr uint32_t AFK_TYPE_CHALLENGE = 1u;
constexpr uint32_t AFK_TYPE_UNLOCK = 2u;
constexpr uint32_t AFK_TYPE_RESULT = 3u;
constexpr uint32_t AFK_RESULT_OK = 0u;
constexpr uint32_t AFK_RESULT_REJECTED = 1u;
constexpr size_t AFK_NONCE_LEN = 32;
constexpr size_t AFK_MAX_UTF16_BYTES = 512;

constexpr wchar_t AFK_PIPE_NAME[] = L"\\\\.\\pipe\\AFKPresenceLock";
