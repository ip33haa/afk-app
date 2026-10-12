# Remove the AFK unlock component, startup shortcut, saved face, and saved password.
# Run in an elevated PowerShell window.
$ErrorActionPreference = "Stop"

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Administrator)) {
    Write-Host "Run uninstall.ps1 as administrator so the unlock component can be removed."
    exit 1
}

Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match "python" -and $_.CommandLine -and $_.CommandLine -match "-m app"
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

$destDll = Join-Path $env:ProgramFiles "AFK\FaceUnlockCP.dll"
if (Test-Path $destDll) {
    & (Join-Path $env:SystemRoot "System32\regsvr32.exe") /u /s $destDll | Out-Null
    Remove-Item $destDll -Force
}

$startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\AFK.cmd"
if (Test-Path $startup) {
    Remove-Item $startup -Force
}

$data = Join-Path $env:LOCALAPPDATA "AFK"
foreach ($name in @("secret.bin", "face.npy")) {
    $path = Join-Path $data $name
    if (Test-Path $path) {
        Remove-Item $path -Force
    }
}

Write-Host "AFK unlock data and the sign-in component were removed."
