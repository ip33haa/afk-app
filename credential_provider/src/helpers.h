#pragma once

#include <windows.h>
#include <ntsecapi.h>

HRESULT PackUnlockLogon(
    LPCWSTR domain,
    LPCWSTR username,
    LPCWSTR password,
    BYTE** outBuffer,
    DWORD* outSize);

HRESULT LookupNegotiatePackage(ULONG* package);

void WipeMemory(void* data, size_t size);
