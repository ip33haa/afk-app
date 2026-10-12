#pragma once

#include <windows.h>
#include <credentialprovider.h>

#include "Credential.h"
#include "PipeServer.h"

class Provider : public ICredentialProvider {
public:
    Provider();
    virtual ~Provider();

    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) override;
    IFACEMETHODIMP_(ULONG) AddRef() override;
    IFACEMETHODIMP_(ULONG) Release() override;
    IFACEMETHODIMP SetUsageScenario(CREDENTIAL_PROVIDER_USAGE_SCENARIO scenario, DWORD flags) override;
    IFACEMETHODIMP SetSerialization(const CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* serialization) override;
    IFACEMETHODIMP Advise(ICredentialProviderEvents* events, UINT_PTR context) override;
    IFACEMETHODIMP UnAdvise() override;
    IFACEMETHODIMP GetFieldDescriptorCount(DWORD* count) override;
    IFACEMETHODIMP GetFieldDescriptorAt(DWORD index, CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR** descriptor) override;
    IFACEMETHODIMP GetCredentialCount(DWORD* count, DWORD* defaultIndex, BOOL* autoLogon) override;
    IFACEMETHODIMP GetCredentialAt(DWORD index, ICredentialProviderCredential** credential) override;

private:
    void OnUnlock(const wchar_t* username, const wchar_t* domain, const wchar_t* password);
    void StartPipe();

    LONG _refs;
    CREDENTIAL_PROVIDER_USAGE_SCENARIO _scenario;
    Credential* _credential;
    PipeServer _pipe;
    ICredentialProviderEvents* _events;
    UINT_PTR _context;
    CRITICAL_SECTION _lock;
};
