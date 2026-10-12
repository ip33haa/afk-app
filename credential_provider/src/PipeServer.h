#pragma once

#include <windows.h>

#include <functional>
#include <thread>

class PipeServer {
public:
    using Callback = std::function<void(const wchar_t* username, const wchar_t* domain, const wchar_t* password)>;

    PipeServer();
    ~PipeServer();

    void Start(Callback callback);
    void Stop();

private:
    void ThreadMain();
    bool ServeOnce();
    bool WaitOverlapped(HANDLE pipe, OVERLAPPED* overlapped, DWORD timeoutMs);
    bool ReadMessage(HANDLE pipe, BYTE* buffer, DWORD capacity, DWORD* read);
    bool WriteMessage(HANDLE pipe, const BYTE* buffer, DWORD size);

    Callback _callback;
    HANDLE _stop;
    std::thread _thread;
    CRITICAL_SECTION _joinLock;
};
