#include <windows.h>
#include <credentialprovider.h>
#include <stdio.h>
#include <new>
#include <unknwn.h>

#include "Provider.h"
#include "guid.h"

HINSTANCE g_instance = nullptr;

const GUID CLSID_AFKFaceUnlock =
    {0x7c2e9a14, 0x6b3f, 0x4f0a, {0x9e, 0x21, 0x4d, 0x8b, 0x5c, 0x6a, 0x1f, 0x30}};

class ClassFactory : public IClassFactory {
public:
    ClassFactory() : _refs(1) {}

    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (ppv == nullptr) {
            return E_INVALIDARG;
        }
        if (riid == __uuidof(IUnknown) || riid == __uuidof(IClassFactory)) {
            *ppv = static_cast<IClassFactory*>(this);
            AddRef();
            return S_OK;
        }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }

    IFACEMETHODIMP_(ULONG) AddRef() override {
        return static_cast<ULONG>(InterlockedIncrement(&_refs));
    }

    IFACEMETHODIMP_(ULONG) Release() override {
        const LONG left = InterlockedDecrement(&_refs);
        if (left == 0) {
            delete this;
        }
        return static_cast<ULONG>(left);
    }

    IFACEMETHODIMP CreateInstance(IUnknown* outer, REFIID riid, void** ppv) override {
        if (ppv == nullptr) {
            return E_INVALIDARG;
        }
        *ppv = nullptr;
        if (outer != nullptr) {
            return CLASS_E_NOAGGREGATION;
        }
        auto* provider = new (std::nothrow) Provider();
        if (provider == nullptr) {
            return E_OUTOFMEMORY;
        }
        const HRESULT hr = provider->QueryInterface(riid, ppv);
        provider->Release();
        return hr;
    }

    IFACEMETHODIMP LockServer(BOOL) override {
        return S_OK;
    }

private:
    LONG _refs;
};

HRESULT SetKeyString(HKEY key, LPCWSTR name, LPCWSTR value) {
    const DWORD bytes = static_cast<DWORD>((wcslen(value) + 1) * sizeof(WCHAR));
    const LSTATUS status = RegSetValueExW(
        key, name, 0, REG_SZ, reinterpret_cast<const BYTE*>(value), bytes);
    return status == ERROR_SUCCESS ? S_OK : HRESULT_FROM_WIN32(status);
}

HRESULT RegisterServer() {
    wchar_t path[MAX_PATH]{};
    if (GetModuleFileNameW(g_instance, path, MAX_PATH) == 0) {
        return HRESULT_FROM_WIN32(GetLastError());
    }
    wchar_t guid[64]{};
    if (StringFromGUID2(CLSID_AFKFaceUnlock, guid, 64) == 0) {
        return E_FAIL;
    }

    wchar_t clsidKey[160]{};
    wchar_t inprocKey[180]{};
    wchar_t providerKey[220]{};
    swprintf_s(clsidKey, L"SOFTWARE\\Classes\\CLSID\\%s", guid);
    swprintf_s(inprocKey, L"SOFTWARE\\Classes\\CLSID\\%s\\InprocServer32", guid);
    swprintf_s(
        providerKey,
        L"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Authentication\\Credential Providers\\%s",
        guid);

    HKEY key = nullptr;
    LSTATUS status = RegCreateKeyExW(HKEY_LOCAL_MACHINE, clsidKey, 0, nullptr, 0, KEY_SET_VALUE, nullptr, &key, nullptr);
    if (status != ERROR_SUCCESS) {
        return HRESULT_FROM_WIN32(status);
    }
    HRESULT hr = SetKeyString(key, nullptr, L"AFK Face Unlock");
    RegCloseKey(key);
    if (FAILED(hr)) {
        return hr;
    }

    status = RegCreateKeyExW(HKEY_LOCAL_MACHINE, inprocKey, 0, nullptr, 0, KEY_SET_VALUE, nullptr, &key, nullptr);
    if (status != ERROR_SUCCESS) {
        return HRESULT_FROM_WIN32(status);
    }
    hr = SetKeyString(key, nullptr, path);
    if (SUCCEEDED(hr)) {
        hr = SetKeyString(key, L"ThreadingModel", L"Apartment");
    }
    RegCloseKey(key);
    if (FAILED(hr)) {
        return hr;
    }

    status = RegCreateKeyExW(HKEY_LOCAL_MACHINE, providerKey, 0, nullptr, 0, KEY_SET_VALUE, nullptr, &key, nullptr);
    if (status != ERROR_SUCCESS) {
        return HRESULT_FROM_WIN32(status);
    }
    hr = SetKeyString(key, nullptr, L"AFK Face Unlock");
    RegCloseKey(key);
    return hr;
}

HRESULT UnregisterServer() {
    wchar_t guid[64]{};
    if (StringFromGUID2(CLSID_AFKFaceUnlock, guid, 64) == 0) {
        return E_FAIL;
    }
    wchar_t clsidKey[160]{};
    wchar_t providerKey[220]{};
    swprintf_s(clsidKey, L"SOFTWARE\\Classes\\CLSID\\%s", guid);
    swprintf_s(
        providerKey,
        L"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Authentication\\Credential Providers\\%s",
        guid);
    RegDeleteTreeW(HKEY_LOCAL_MACHINE, clsidKey);
    RegDeleteTreeW(HKEY_LOCAL_MACHINE, providerKey);
    return S_OK;
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        g_instance = module;
        DisableThreadLibraryCalls(module);
    }
    return TRUE;
}

STDAPI DllGetClassObject(REFCLSID clsid, REFIID riid, void** ppv) {
    if (ppv == nullptr) {
        return E_INVALIDARG;
    }
    *ppv = nullptr;
    if (clsid != CLSID_AFKFaceUnlock) {
        return CLASS_E_CLASSNOTAVAILABLE;
    }
    auto* factory = new (std::nothrow) ClassFactory();
    if (factory == nullptr) {
        return E_OUTOFMEMORY;
    }
    const HRESULT hr = factory->QueryInterface(riid, ppv);
    factory->Release();
    return hr;
}

STDAPI DllCanUnloadNow() {
    return S_FALSE;
}

STDAPI DllRegisterServer() {
    return RegisterServer();
}

STDAPI DllUnregisterServer() {
    return UnregisterServer();
}
