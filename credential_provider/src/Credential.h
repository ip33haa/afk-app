#pragma once

#include <windows.h>
#include <credentialprovider.h>

class Credential : public ICredentialProviderCredential {
public:
    Credential();
    virtual ~Credential();

    void SetSecret(LPCWSTR username, LPCWSTR domain, LPCWSTR password);
    void SetFailureHandler(void (*handler)(void* context), void* context);
    bool HasSecret();
    bool TakeSecret(wchar_t* username, wchar_t* domain, wchar_t* password, size_t cch);

    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) override;
    IFACEMETHODIMP_(ULONG) AddRef() override;
    IFACEMETHODIMP_(ULONG) Release() override;
    IFACEMETHODIMP Advise(ICredentialProviderCredentialEvents* events) override;
    IFACEMETHODIMP UnAdvise() override;
    IFACEMETHODIMP SetSelected(BOOL* autoLogon) override;
    IFACEMETHODIMP SetDeselected() override;
    IFACEMETHODIMP GetFieldState(
        DWORD fieldId,
        CREDENTIAL_PROVIDER_FIELD_STATE* state,
        CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE* interactive) override;
    IFACEMETHODIMP GetStringValue(DWORD fieldId, LPWSTR* value) override;
    IFACEMETHODIMP GetBitmapValue(DWORD fieldId, HBITMAP* bitmap) override;
    IFACEMETHODIMP GetCheckboxValue(DWORD fieldId, BOOL* checked, LPWSTR* label) override;
    IFACEMETHODIMP GetSubmitButtonValue(DWORD fieldId, DWORD* adjacentTo) override;
    IFACEMETHODIMP GetComboBoxValueCount(DWORD fieldId, DWORD* items, DWORD* selected) override;
    IFACEMETHODIMP GetComboBoxValueAt(DWORD fieldId, DWORD item, LPWSTR* value) override;
    IFACEMETHODIMP SetStringValue(DWORD fieldId, LPCWSTR value) override;
    IFACEMETHODIMP SetCheckboxValue(DWORD fieldId, BOOL checked) override;
    IFACEMETHODIMP SetComboBoxSelectedValue(DWORD fieldId, DWORD selected) override;
    IFACEMETHODIMP CommandLinkClicked(DWORD fieldId) override;
    IFACEMETHODIMP GetSerialization(
        CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE* response,
        CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* serialization,
        LPWSTR* optionalStatus,
        CREDENTIAL_PROVIDER_STATUS_ICON* optionalIcon) override;
    IFACEMETHODIMP ReportResult(
        NTSTATUS status,
        NTSTATUS substatus,
        LPWSTR* optionalStatus,
        CREDENTIAL_PROVIDER_STATUS_ICON* optionalIcon) override;

private:
    void WipeSecret();

    LONG _refs;
    CRITICAL_SECTION _lock;
    HBITMAP _bitmap;
    wchar_t _username[257];
    wchar_t _domain[257];
    wchar_t _password[257];
    bool _hasSecret;
    void (*_onFailure)(void*);
    void* _failureContext;
};
