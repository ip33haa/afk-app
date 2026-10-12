# AFK setup. Run this in an elevated PowerShell window:
#   powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Find-Python {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($version in @("-3.12", "-3.13", "-3.11", "-3.14", "-3")) {
            $exe = & py $version -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe) {
                return $exe.Trim()
            }
        }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }
    throw "Python 3.11 or newer is required."
}

Write-Host "Creating the AFK Python environment"
$python = Find-Python
& $python -m venv (Join-Path $root ".venv")
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip could not be upgraded." }
& $venvPython -m pip install -r (Join-Path $root "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Python dependencies could not be installed." }
& $venvPython -m app.models
if ($LASTEXITCODE -ne 0) { throw "Face models could not be downloaded." }
& $venvPython -c "from app.startup import set_start_with_windows; set_start_with_windows(True)"

if (-not (Test-Administrator)) {
    Write-Host ""
    Write-Host "The tray app is ready, but camera unlock is not installed."
    Write-Host "Windows will not unlock unless this script is run as administrator."
    Write-Host "Open PowerShell as administrator and run:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit 1
}

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vs = $null
if (Test-Path $vswhere) {
    $vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
}
if (-not $vs) {
    Write-Host ""
    Write-Host "Visual Studio C++ build tools are required to build the unlock component."
    Write-Host "Install Desktop development with C++ from:"
    Write-Host "https://visualstudio.microsoft.com/visual-cpp-build-tools/"
    exit 1
}

$vsDevCmd = Join-Path $vs "Common7\Tools\VsDevCmd.bat"
$build = Join-Path $root "credential_provider\build"
Write-Host "Building the unlock component"
cmd /c "`"$vsDevCmd`" -arch=x64 -host_arch=x64 && cmake -S `"$root\credential_provider`" -B `"$build`" -A x64 && cmake --build `"$build`" --config Release"
if ($LASTEXITCODE -ne 0) {
    throw "The unlock component failed to build."
}

$dll = @(
    (Join-Path $build "Release\FaceUnlockCP.dll"),
    (Join-Path $build "FaceUnlockCP.dll")
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $dll) {
    throw "FaceUnlockCP.dll was not produced."
}

$dest = Join-Path $env:ProgramFiles "AFK"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
$destDll = Join-Path $dest "FaceUnlockCP.dll"
$regsvr = Join-Path $env:SystemRoot "System32\regsvr32.exe"
if (Test-Path $destDll) {
    & $regsvr /u /s $destDll | Out-Null
}
Copy-Item $dll $destDll -Force
& $regsvr /s $destDll
if ($LASTEXITCODE -ne 0) {
    throw "Could not register the unlock component (regsvr32 exit $LASTEXITCODE)."
}

Write-Host "AFK is installed. Starting the tray app."
$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
Start-Process $pythonw -ArgumentList "-m", "app" -WorkingDirectory $root
