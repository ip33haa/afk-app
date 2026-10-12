#include "Credential.h"

#include "guid.h"
#include "helpers.h"

#include <shlwapi.h>

namespace {
enum FieldId : DWORD {
    SFI_TILE = 0,
    SFI_LABEL = 1,
    SFI_STATUS = 2,
    SFI_COUNT = 3,
};
}

Credential::Credential() : _refs(1), _bitmap(nullptr), _hasSecret(false), _onFailure(nullptr), _failureContext(nullptr) {
    InitializeCriticalSection(&_lock);
    ZeroMemory(_username, sizeof(_username));
    ZeroMemory(_domain, sizeof(_domain));
    ZeroMemory(_password, sizeof(_password));

    BITMAPINFO info{};
    info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth = 48;
    info.bmiHeader.biHeight = -48;
    info.bmiHeader.biPlanes = 1;
    info.bmiHeader.biBitCount = 32;
    info.bmiHeader.biCompression = BI_RGB;
    void* bits = nullptr;
    HDC screen = GetDC(nullptr);
    _bitmap = CreateDIBSection(screen, &info, DIB_RGB_COLORS, &bits, nullptr, 0);
    ReleaseDC(nullptr, screen);
    if (_bitmap != nullptr && bits != nullptr) {
        auto* pixels = static_cast<uint32_t*>(bits);
        for (int y = 0; y < 48; ++y) {
            for (int x = 0; x < 48; ++x) {
                const int dx = x - 24;
                const int dy = y - 24;
                pixels[y * 48 + x] = (dx * dx + dy * dy <= 18 * 18) ? 0xFF2E8B57u : 0xFF1B1B1Bu;
            }
        }
    }
}

Credential::~Credential() {
    WipeSecret();
    if (_bitmap != nullptr) {
        DeleteObject(_bitmap);
    }
    DeleteCriticalSection(&_lock);
}

void Credential::SetSecret(LPCWSTR username, LPCWSTR domain, LPCWSTR password) {
    EnterCriticalSection(&_lock);
    WipeSecret();
    if (username != nullptr && domain != nullptr && password != nullptr && password[0] != L'\0') {
        wcsncpy_s(_username, username, _TRUNCATE);
        wcsncpy_s(_domain, domain, _TRUNCATE);
        wcsncpy_s(_password, password, _TRUNCATE);
        _hasSecret = _password[0] != L'\0' && _username[0] != L'\0';
    }
    LeaveCriticalSection(&_lock);
}

void Credential::SetFailureHandler(void (*handler)(void* context), void* context) {
    _onFailure = handler;
    _failureContext = context;
}

bool Credential::HasSecret() {
    EnterCriticalSection(&_lock);
    const bool has = _hasSecret;
    LeaveCriticalSection(&_lock);
    return has;
}

bool Credential::TakeSecret(wchar_t* username, wchar_t* domain, wchar_t* password, size_t cch) {
    if (username == nullptr || domain == nullptr || password == nullptr || cch < 2) {
        return false;
    }
    EnterCriticalSection(&_lock);
    const bool ok = _hasSecret;
    if (ok) {
        wcsncpy_s(username, cch, _username, _TRUNCATE);
        wcsncpy_s(domain, cch, _domain, _TRUNCATE);
        wcsncpy_s(password, cch, _password, _TRUNCATE);
        WipeSecret();
    }
    LeaveCriticalSection(&_lock);
    return ok;
}

void Credential::WipeSecret() {
    WipeMemory(_username, sizeof(_username));
    WipeMemory(_domain, sizeof(_domain));
    WipeMemory(_password, sizeof(_password));
    _hasSecret = false;
}

IFACEMETHODIMP Credential::QueryInterface(REFIID riid, void** ppv) {
    if (ppv == nullptr) {
        return E_INVALIDARG;
    }
    if (riid == __uuidof(IUnknown) || riid == __uuidof(ICredentialProviderCredential)) {
        *ppv = static_cast<ICredentialProviderCredential*>(this);
        AddRef();
        return S_OK;
    }
    *ppv = nullptr;
    return E_NOINTERFACE;
}

IFACEMETHODIMP_(ULONG) Credential::AddRef() {
    return static_cast<ULONG>(InterlockedIncrement(&_refs));
}

IFACEMETHODIMP_(ULONG) Credential::Release() {
    const LONG left = InterlockedDecrement(&_refs);
    if (left == 0) {
        delete this;
    }
    return static_cast<ULONG>(left);
}

IFACEMETHODIMP Credential::Advise(ICredentialProviderCredentialEvents*) {
    return S_OK;
}

IFACEMETHODIMP Credential::UnAdvise() {
    return S_OK;
}

IFACEMETHODIMP Credential::SetSelected(BOOL* autoLogon) {
    if (autoLogon == nullptr) {
        return E_INVALIDARG;
    }
    *autoLogon = HasSecret() ? TRUE : FALSE;
    return S_OK;
}

IFACEMETHODIMP Credential::SetDeselected() {
    return S_OK;
}

IFACEMETHODIMP Credential::GetFieldState(
    DWORD fieldId,
    CREDENTIAL_PROVIDER_FIELD_STATE* state,
    CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE* interactive) {
    if (state == nullptr || interactive == nullptr || fieldId >= SFI_COUNT) {
        return E_INVALIDARG;
    }
    *state = CPFS_DISPLAY_IN_BOTH;
    *interactive = CPFIS_NONE;
    return S_OK;
}

IFACEMETHODIMP Credential::GetStringValue(DWORD fieldId, LPWSTR* value) {
    if (value == nullptr) {
        return E_INVALIDARG;
    }
    *value = nullptr;
    if (fieldId == SFI_LABEL) {
        return SHStrDupW(L"AFK", value);
    }
    if (fieldId == SFI_STATUS) {
        return SHStrDupW(L"Looking at the camera", value);
    }
    return E_INVALIDARG;
}

IFACEMETHODIMP Credential::GetBitmapValue(DWORD fieldId, HBITMAP* bitmap) {
    if (bitmap == nullptr) {
        return E_INVALIDARG;
    }
    *bitmap = nullptr;
    if (fieldId != SFI_TILE || _bitmap == nullptr) {
        return E_INVALIDARG;
    }
    *bitmap = _bitmap;
    return S_OK;
}

IFACEMETHODIMP Credential::GetCheckboxValue(DWORD, BOOL*, LPWSTR*) { return E_NOTIMPL; }
IFACEMETHODIMP Credential::GetSubmitButtonValue(DWORD, DWORD*) { return E_NOTIMPL; }
IFACEMETHODIMP Credential::GetComboBoxValueCount(DWORD, DWORD*, DWORD*) { return E_NOTIMPL; }
IFACEMETHODIMP Credential::GetComboBoxValueAt(DWORD, DWORD, LPWSTR*) { return E_NOTIMPL; }
IFACEMETHODIMP Credential::SetStringValue(DWORD, LPCWSTR) { return E_NOTIMPL; }
IFACEMETHODIMP Credential::SetCheckboxValue(DWORD, BOOL) { return E_NOTIMPL; }
IFACEMETHODIMP Credential::SetComboBoxSelectedValue(DWORD, DWORD) { return E_NOTIMPL; }
IFACEMETHODIMP Credential::CommandLinkClicked(DWORD) { return E_NOTIMPL; }

IFACEMETHODIMP Credential::GetSerialization(
    CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE* response,
    CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* serialization,
    LPWSTR* optionalStatus,
    CREDENTIAL_PROVIDER_STATUS_ICON* optionalIcon) {
    if (response == nullptr || serialization == nullptr || optionalStatus == nullptr || optionalIcon == nullptr) {
        return E_INVALIDARG;
    }
    *response = CPGSR_NO_CREDENTIAL_NOT_FINISHED;
    *optionalStatus = nullptr;
    *optionalIcon = CPSI_NONE;
    ZeroMemory(serialization, sizeof(*serialization));

    wchar_t username[257]{};
    wchar_t domain[257]{};
    wchar_t password[257]{};
    if (!TakeSecret(username, domain, password, 257)) {
        return E_UNEXPECTED;
    }

    BYTE* buffer = nullptr;
    DWORD size = 0;
    HRESULT hr = PackUnlockLogon(domain, username, password, &buffer, &size);
    ULONG package = 0;
    if (SUCCEEDED(hr)) {
        hr = LookupNegotiatePackage(&package);
    }
    WipeMemory(username, sizeof(username));
    WipeMemory(domain, sizeof(domain));
    WipeMemory(password, sizeof(password));
    if (FAILED(hr)) {
        if (buffer != nullptr) {
            WipeMemory(buffer, size);
            CoTaskMemFree(buffer);
        }
        return hr;
    }

    serialization->ulAuthenticationPackage = package;
    serialization->clsidCredentialProvider = CLSID_AFKFaceUnlock;
    serialization->cbSerialization = size;
    serialization->rgbSerialization = buffer;
    *response = CPGSR_RETURN_CREDENTIAL_FINISHED;
    return S_OK;
}

IFACEMETHODIMP Credential::ReportResult(
    NTSTATUS status,
    NTSTATUS,
    LPWSTR* optionalStatus,
    CREDENTIAL_PROVIDER_STATUS_ICON* optionalIcon) {
    if (optionalStatus != nullptr) {
        *optionalStatus = nullptr;
    }
    if (optionalIcon != nullptr) {
        *optionalIcon = CPSI_NONE;
    }
    WipeSecret();
    if (status != 0 && _onFailure != nullptr) {
        _onFailure(_failureContext);
    }
    return S_OK;
}
