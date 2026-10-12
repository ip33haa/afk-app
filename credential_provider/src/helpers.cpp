#include "helpers.h"

#include "protocol.h"

#include <cstring>

void WipeMemory(void* data, size_t size) {
    if (data != nullptr && size > 0) {
        SecureZeroMemory(data, size);
    }
}

HRESULT PackUnlockLogon(
    LPCWSTR domain,
    LPCWSTR username,
    LPCWSTR password,
    BYTE** outBuffer,
    DWORD* outSize) {
    if (domain == nullptr || username == nullptr || password == nullptr ||
        outBuffer == nullptr || outSize == nullptr) {
        return E_INVALIDARG;
    }
    *outBuffer = nullptr;
    *outSize = 0;

    const DWORD domainBytes = static_cast<DWORD>(wcslen(domain) * sizeof(WCHAR));
    const DWORD userBytes = static_cast<DWORD>(wcslen(username) * sizeof(WCHAR));
    const DWORD passBytes = static_cast<DWORD>(wcslen(password) * sizeof(WCHAR));
    if (userBytes == 0 || passBytes == 0 ||
        domainBytes > AFK_MAX_UTF16_BYTES || userBytes > AFK_MAX_UTF16_BYTES ||
        passBytes > AFK_MAX_UTF16_BYTES) {
        return E_INVALIDARG;
    }

    const DWORD total = sizeof(KERB_INTERACTIVE_UNLOCK_LOGON) + domainBytes + userBytes + passBytes;
    auto* packed = static_cast<KERB_INTERACTIVE_UNLOCK_LOGON*>(CoTaskMemAlloc(total));
    if (packed == nullptr) {
        return E_OUTOFMEMORY;
    }
    ZeroMemory(packed, total);
    packed->Logon.MessageType = KerbWorkstationUnlockLogon;

    BYTE* cursor = reinterpret_cast<BYTE*>(packed) + sizeof(KERB_INTERACTIVE_UNLOCK_LOGON);
    auto place = [&](UNICODE_STRING* field, LPCWSTR source, DWORD bytes) {
        if (bytes == 0) {
            field->Length = 0;
            field->MaximumLength = 0;
            field->Buffer = nullptr;
            return;
        }
        memcpy(cursor, source, bytes);
        field->Length = static_cast<USHORT>(bytes);
        field->MaximumLength = static_cast<USHORT>(bytes);
        field->Buffer = reinterpret_cast<PWSTR>(static_cast<ULONG_PTR>(cursor - reinterpret_cast<BYTE*>(packed)));
        cursor += bytes;
    };

    place(&packed->Logon.LogonDomainName, domain, domainBytes);
    place(&packed->Logon.UserName, username, userBytes);
    place(&packed->Logon.Password, password, passBytes);

    *outBuffer = reinterpret_cast<BYTE*>(packed);
    *outSize = total;
    return S_OK;
}

HRESULT LookupNegotiatePackage(ULONG* package) {
    if (package == nullptr) {
        return E_INVALIDARG;
    }
    HANDLE lsa = nullptr;
    NTSTATUS status = LsaConnectUntrusted(&lsa);
    if (status < 0) {
        return HRESULT_FROM_NT(status);
    }

    char nameBytes[] = "Negotiate";
    LSA_STRING name{};
    name.Buffer = nameBytes;
    name.Length = static_cast<USHORT>(sizeof(nameBytes) - 1);
    name.MaximumLength = static_cast<USHORT>(sizeof(nameBytes));

    status = LsaLookupAuthenticationPackage(lsa, &name, package);
    LsaDeregisterLogonProcess(lsa);
    if (status < 0) {
        return HRESULT_FROM_NT(status);
    }
    return S_OK;
}
