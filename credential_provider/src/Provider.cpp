#include "Provider.h"

#include <shlwapi.h>

namespace {
struct Field {
    DWORD id;
    CREDENTIAL_PROVIDER_FIELD_TYPE type;
    LPCWSTR label;
};

const Field kFields[] = {
    {0, CPFT_TILE_IMAGE, L"Image"},
    {1, CPFT_LARGE_TEXT, L"Label"},
    {2, CPFT_SMALL_TEXT, L"Status"},
};
}

Provider::Provider()
    : _refs(1),
      _scenario(CPUS_INVALID),
      _credential(new Credential()),
      _events(nullptr),
      _context(0) {
    InitializeCriticalSection(&_lock);
}

Provider::~Provider() {
    _pipe.Stop();
    if (_events != nullptr) {
        _events->Release();
        _events = nullptr;
    }
    if (_credential != nullptr) {
        _credential->Release();
        _credential = nullptr;
    }
    DeleteCriticalSection(&_lock);
}

void Provider::StartPipe() {
    _pipe.Start([this](const wchar_t* username, const wchar_t* domain, const wchar_t* password) {
        OnUnlock(username, domain, password);
    });
}

void Provider::OnUnlock(const wchar_t* username, const wchar_t* domain, const wchar_t* password) {
    _credential->SetSecret(username, domain, password);
    ICredentialProviderEvents* events = nullptr;
    UINT_PTR context = 0;
    EnterCriticalSection(&_lock);
    events = _events;
    if (events != nullptr) {
        events->AddRef();
    }
    context = _context;
    LeaveCriticalSection(&_lock);
    if (events != nullptr) {
        events->CredentialsChanged(context);
        events->Release();
    }
}

IFACEMETHODIMP Provider::QueryInterface(REFIID riid, void** ppv) {
    if (ppv == nullptr) {
        return E_INVALIDARG;
    }
    if (riid == __uuidof(IUnknown) || riid == __uuidof(ICredentialProvider)) {
        *ppv = static_cast<ICredentialProvider*>(this);
        AddRef();
        return S_OK;
    }
    *ppv = nullptr;
    return E_NOINTERFACE;
}

IFACEMETHODIMP_(ULONG) Provider::AddRef() {
    return static_cast<ULONG>(InterlockedIncrement(&_refs));
}

IFACEMETHODIMP_(ULONG) Provider::Release() {
    const LONG left = InterlockedDecrement(&_refs);
    if (left == 0) {
        delete this;
    }
    return static_cast<ULONG>(left);
}

IFACEMETHODIMP Provider::SetUsageScenario(CREDENTIAL_PROVIDER_USAGE_SCENARIO scenario, DWORD) {
    if (scenario != CPUS_UNLOCK_WORKSTATION) {
        return E_NOTIMPL;
    }
    _scenario = scenario;
    return S_OK;
}

IFACEMETHODIMP Provider::SetSerialization(const CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION*) {
    return E_NOTIMPL;
}

IFACEMETHODIMP Provider::Advise(ICredentialProviderEvents* events, UINT_PTR context) {
    EnterCriticalSection(&_lock);
    if (_events != nullptr) {
        _events->Release();
    }
    _events = events;
    if (_events != nullptr) {
        _events->AddRef();
    }
    _context = context;
    LeaveCriticalSection(&_lock);
    if (_scenario == CPUS_UNLOCK_WORKSTATION) {
        StartPipe();
    }
    return S_OK;
}

IFACEMETHODIMP Provider::UnAdvise() {
    _pipe.Stop();
    EnterCriticalSection(&_lock);
    if (_events != nullptr) {
        _events->Release();
        _events = nullptr;
    }
    _context = 0;
    LeaveCriticalSection(&_lock);
    return S_OK;
}

IFACEMETHODIMP Provider::GetFieldDescriptorCount(DWORD* count) {
    if (count == nullptr) {
        return E_INVALIDARG;
    }
    *count = static_cast<DWORD>(sizeof(kFields) / sizeof(kFields[0]));
    return S_OK;
}

IFACEMETHODIMP Provider::GetFieldDescriptorAt(DWORD index, CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR** descriptor) {
    if (descriptor == nullptr || index >= sizeof(kFields) / sizeof(kFields[0])) {
        return E_INVALIDARG;
    }
    *descriptor = nullptr;
    auto* copy = static_cast<CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR*>(
        CoTaskMemAlloc(sizeof(CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR)));
    if (copy == nullptr) {
        return E_OUTOFMEMORY;
    }
    ZeroMemory(copy, sizeof(*copy));
    copy->dwFieldID = kFields[index].id;
    copy->cpft = kFields[index].type;
    copy->guidFieldType = GUID_NULL;
    const HRESULT hr = SHStrDupW(kFields[index].label, &copy->pszLabel);
    if (FAILED(hr)) {
        CoTaskMemFree(copy);
        return hr;
    }
    *descriptor = copy;
    return S_OK;
}

IFACEMETHODIMP Provider::GetCredentialCount(DWORD* count, DWORD* defaultIndex, BOOL* autoLogon) {
    if (count == nullptr || defaultIndex == nullptr || autoLogon == nullptr) {
        return E_INVALIDARG;
    }
    if (_credential != nullptr && _credential->HasSecret()) {
        *count = 1;
        *defaultIndex = 0;
        *autoLogon = TRUE;
    } else {
        *count = 0;
        *defaultIndex = CREDENTIAL_PROVIDER_NO_DEFAULT;
        *autoLogon = FALSE;
    }
    return S_OK;
}

IFACEMETHODIMP Provider::GetCredentialAt(DWORD index, ICredentialProviderCredential** credential) {
    if (credential == nullptr) {
        return E_INVALIDARG;
    }
    *credential = nullptr;
    if (index != 0 || _credential == nullptr || !_credential->HasSecret()) {
        return E_INVALIDARG;
    }
    return _credential->QueryInterface(__uuidof(ICredentialProviderCredential), reinterpret_cast<void**>(credential));
}
