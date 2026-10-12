#include "PipeServer.h"

#include "protocol.h"

#include <bcrypt.h>
#include <sddl.h>
#include <wtsapi32.h>

#include <cstdint>
#include <cstring>
#include <string>

namespace {

struct UnlockFields {
    wchar_t username[257];
    wchar_t domain[257];
    wchar_t password[257];
};

bool ReadU32(const BYTE*& cursor, const BYTE* end, uint32_t* value) {
    if (static_cast<size_t>(end - cursor) < sizeof(uint32_t)) {
        return false;
    }
    memcpy(value, cursor, sizeof(uint32_t));
    cursor += sizeof(uint32_t);
    return true;
}

bool ReadWide(const BYTE*& cursor, const BYTE* end, wchar_t* dest, size_t capacity) {
    uint32_t bytes = 0;
    if (!ReadU32(cursor, end, &bytes)) {
        return false;
    }
    if (bytes > AFK_MAX_UTF16_BYTES || (bytes % sizeof(wchar_t)) != 0) {
        return false;
    }
    if (static_cast<size_t>(end - cursor) < bytes) {
        return false;
    }
    const size_t chars = bytes / sizeof(wchar_t);
    if (chars >= capacity) {
        return false;
    }
    memcpy(dest, cursor, bytes);
    dest[chars] = L'\0';
    cursor += bytes;
    return true;
}

bool ParseUnlock(const BYTE* data, DWORD size, const BYTE nonce[AFK_NONCE_LEN], UnlockFields* out) {
    ZeroMemory(out, sizeof(*out));
    const BYTE* cursor = data;
    const BYTE* end = data + size;
    uint32_t magic = 0;
    uint32_t type = 0;
    if (!ReadU32(cursor, end, &magic) || !ReadU32(cursor, end, &type)) {
        return false;
    }
    if (magic != AFK_MAGIC || type != AFK_TYPE_UNLOCK) {
        return false;
    }
    if (static_cast<size_t>(end - cursor) < AFK_NONCE_LEN) {
        return false;
    }
    unsigned diff = 0;
    for (size_t i = 0; i < AFK_NONCE_LEN; ++i) {
        diff |= static_cast<unsigned>(cursor[i] ^ nonce[i]);
    }
    cursor += AFK_NONCE_LEN;
    if (diff != 0) {
        return false;
    }
    if (!ReadWide(cursor, end, out->username, 257) ||
        !ReadWide(cursor, end, out->domain, 257) ||
        !ReadWide(cursor, end, out->password, 257)) {
        return false;
    }
    return cursor == end && out->username[0] != L'\0' && out->password[0] != L'\0';
}

bool BuildPipeSecurity(SECURITY_ATTRIBUTES* attributes, PSECURITY_DESCRIPTOR* descriptor) {
    *descriptor = nullptr;
    attributes->nLength = sizeof(*attributes);
    attributes->bInheritHandle = FALSE;
    attributes->lpSecurityDescriptor = nullptr;

    DWORD sessionId = WTSGetActiveConsoleSessionId();
    HANDLE token = nullptr;
    if (sessionId == 0xFFFFFFFF || !WTSQueryUserToken(sessionId, &token)) {
        return false;
    }

    DWORD needed = 0;
    GetTokenInformation(token, TokenUser, nullptr, 0, &needed);
    if (needed == 0) {
        CloseHandle(token);
        return false;
    }
    auto* user = static_cast<TOKEN_USER*>(LocalAlloc(LMEM_FIXED, needed));
    if (user == nullptr || !GetTokenInformation(token, TokenUser, user, needed, &needed)) {
        LocalFree(user);
        CloseHandle(token);
        return false;
    }
    CloseHandle(token);

    LPWSTR sid = nullptr;
    const BOOL converted = ConvertSidToStringSidW(user->User.Sid, &sid);
    LocalFree(user);
    if (!converted || sid == nullptr) {
        return false;
    }

    // SYSTEM and the signed-in user can use the pipe. Medium integrity lets the
    // user-session app write to a pipe created by the lock screen.
    std::wstring sddl = L"D:(A;;GA;;;SY)(A;;GRGW;;;";
    sddl += sid;
    sddl += L")S:(ML;;NW;;;ME)";
    LocalFree(sid);

    if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl.c_str(), SDDL_REVISION_1, descriptor, nullptr)) {
        return false;
    }
    attributes->lpSecurityDescriptor = *descriptor;
    return true;
}

}  // namespace

PipeServer::PipeServer() : _stop(CreateEventW(nullptr, TRUE, FALSE, nullptr)) {
    InitializeCriticalSection(&_joinLock);
}

PipeServer::~PipeServer() {
    Stop();
    if (_stop != nullptr) {
        CloseHandle(_stop);
    }
    DeleteCriticalSection(&_joinLock);
}

void PipeServer::Start(Callback callback) {
    Stop();
    ResetEvent(_stop);
    _callback = std::move(callback);
    _thread = std::thread([this] { ThreadMain(); });
}

void PipeServer::Stop() {
    if (_stop != nullptr) {
        SetEvent(_stop);
    }
    EnterCriticalSection(&_joinLock);
    if (_thread.joinable() && _thread.get_id() != std::this_thread::get_id()) {
        _thread.join();
    }
    LeaveCriticalSection(&_joinLock);
}

void PipeServer::ThreadMain() {
    while (WaitForSingleObject(_stop, 0) != WAIT_OBJECT_0) {
        ServeOnce();
    }
}

bool PipeServer::ServeOnce() {
    SECURITY_ATTRIBUTES security{};
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    if (!BuildPipeSecurity(&security, &descriptor)) {
        OutputDebugStringW(L"AFK credential provider could not build the pipe ACL\n");
        WaitForSingleObject(_stop, 500);
        return false;
    }

    HANDLE pipe = CreateNamedPipeW(
        AFK_PIPE_NAME,
        PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED,
        PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
        1,
        4096,
        4096,
        0,
        &security);
    LocalFree(descriptor);
    if (pipe == INVALID_HANDLE_VALUE) {
        WaitForSingleObject(_stop, 500);
        return false;
    }

    OVERLAPPED connect{};
    connect.hEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    bool connected = false;
    if (connect.hEvent != nullptr) {
        const BOOL ok = ConnectNamedPipe(pipe, &connect);
        if (ok) {
            connected = true;
        } else {
            const DWORD err = GetLastError();
            if (err == ERROR_PIPE_CONNECTED) {
                connected = true;
            } else if (err == ERROR_IO_PENDING) {
                connected = WaitOverlapped(pipe, &connect, INFINITE);
            }
        }
    }

    bool accepted = false;
    if (connected && WaitForSingleObject(_stop, 0) != WAIT_OBJECT_0) {
        BYTE nonce[AFK_NONCE_LEN]{};
        if (BCryptGenRandom(nullptr, nonce, sizeof(nonce), BCRYPT_USE_SYSTEM_PREFERRED_RNG) == 0) {
            BYTE challenge[8 + AFK_NONCE_LEN]{};
            const uint32_t magic = AFK_MAGIC;
            const uint32_t type = AFK_TYPE_CHALLENGE;
            memcpy(challenge, &magic, sizeof(magic));
            memcpy(challenge + 4, &type, sizeof(type));
            memcpy(challenge + 8, nonce, sizeof(nonce));
            BYTE incoming[4096]{};
            DWORD incomingSize = 0;
            if (WriteMessage(pipe, challenge, sizeof(challenge)) &&
                ReadMessage(pipe, incoming, sizeof(incoming), &incomingSize)) {
                UnlockFields fields{};
                const bool parsed = ParseUnlock(incoming, incomingSize, nonce, &fields);
                SecureZeroMemory(incoming, sizeof(incoming));
                if (parsed) {
                    BYTE result[12]{};
                    const uint32_t resultMagic = AFK_MAGIC;
                    const uint32_t resultType = AFK_TYPE_RESULT;
                    const uint32_t code = AFK_RESULT_OK;
                    memcpy(result, &resultMagic, 4);
                    memcpy(result + 4, &resultType, 4);
                    memcpy(result + 8, &code, 4);
                    if (WriteMessage(pipe, result, sizeof(result)) && _callback) {
                        _callback(fields.username, fields.domain, fields.password);
                        accepted = true;
                    }
                } else {
                    BYTE result[12]{};
                    const uint32_t resultMagic = AFK_MAGIC;
                    const uint32_t resultType = AFK_TYPE_RESULT;
                    const uint32_t code = AFK_RESULT_REJECTED;
                    memcpy(result, &resultMagic, 4);
                    memcpy(result + 4, &resultType, 4);
                    memcpy(result + 8, &code, 4);
                    WriteMessage(pipe, result, sizeof(result));
                }
                SecureZeroMemory(&fields, sizeof(fields));
            }
        }
    }

    if (connect.hEvent != nullptr) {
        CloseHandle(connect.hEvent);
    }
    DisconnectNamedPipe(pipe);
    CloseHandle(pipe);
    return accepted;
}

bool PipeServer::WaitOverlapped(HANDLE pipe, OVERLAPPED* overlapped, DWORD timeoutMs) {
    HANDLE waits[2] = {_stop, overlapped->hEvent};
    const DWORD which = WaitForMultipleObjects(2, waits, FALSE, timeoutMs);
    if (which != WAIT_OBJECT_0 + 1) {
        CancelIoEx(pipe, overlapped);
        return false;
    }
    DWORD transferred = 0;
    return GetOverlappedResult(pipe, overlapped, &transferred, FALSE) == TRUE;
}

bool PipeServer::ReadMessage(HANDLE pipe, BYTE* buffer, DWORD capacity, DWORD* read) {
    OVERLAPPED overlapped{};
    overlapped.hEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (overlapped.hEvent == nullptr) {
        return false;
    }
    DWORD transferred = 0;
    const BOOL ok = ReadFile(pipe, buffer, capacity, &transferred, &overlapped);
    bool success = false;
    if (ok) {
        success = true;
    } else if (GetLastError() == ERROR_IO_PENDING) {
        success = WaitOverlapped(pipe, &overlapped, 5000);
        if (success) {
            GetOverlappedResult(pipe, &overlapped, &transferred, FALSE);
        }
    }
    CloseHandle(overlapped.hEvent);
    if (success && read != nullptr) {
        *read = transferred;
    }
    return success && transferred > 0;
}

bool PipeServer::WriteMessage(HANDLE pipe, const BYTE* buffer, DWORD size) {
    OVERLAPPED overlapped{};
    overlapped.hEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (overlapped.hEvent == nullptr) {
        return false;
    }
    DWORD transferred = 0;
    const BOOL ok = WriteFile(pipe, buffer, size, &transferred, &overlapped);
    bool success = ok == TRUE;
    if (!success && GetLastError() == ERROR_IO_PENDING) {
        success = WaitOverlapped(pipe, &overlapped, 5000);
    }
    CloseHandle(overlapped.hEvent);
    return success;
}
