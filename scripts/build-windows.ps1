# EQ Legends BiS Windows build
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
Write-Host "app root $Root"

function Exit-OnNativeFailure {
    param([Parameter(Mandatory = $true)][string]$Step)
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $Step (exit code $LASTEXITCODE)"
        exit $LASTEXITCODE
    }
}

Push-Location frontend
if (-not (Test-Path node_modules)) {
    npm install
    Exit-OnNativeFailure "frontend npm install"
}
npm run build
Exit-OnNativeFailure "frontend npm run build"
Pop-Location
if (-not (Test-Path .\.venv\Scripts\python.exe)) {
    py -3 -m venv .venv
    Exit-OnNativeFailure "py -3 -m venv .venv"
}
$Vpy = ".\.venv\Scripts\python.exe"
& $Vpy -m pip install -U pip
Exit-OnNativeFailure "pip install -U pip"
& $Vpy -m pip install -r backend\requirements.txt pyinstaller
Exit-OnNativeFailure "pip install -r backend\requirements.txt pyinstaller"
# Drop untracked and ignored leftovers in the packaging inputs.
# Tracked source (icons, installer.nsh, committed resources) stays.
# This runs before bundling so electron-builder packs a fresh copy.
# A dirty tree made the 1.1.11 installer about 690 KB larger than a clean build.
Write-Host "cleaning stale outputs in desktop/build and desktop/resources"
& git clean -fdx -- desktop/build desktop/resources
Exit-OnNativeFailure "git clean desktop/build desktop/resources"
& $Vpy scripts\bundle_desktop_resources.py
Exit-OnNativeFailure "scripts\bundle_desktop_resources.py"
& $Vpy -m PyInstaller --noconfirm backend\packaging\eq-api.spec
Exit-OnNativeFailure "PyInstaller backend\packaging\eq-api.spec"
$ApiDist = Join-Path $Root "dist\eq-api"
$ResApi = Join-Path $Root "desktop\resources\eq-api"
if (-not (Test-Path (Join-Path $ApiDist "eq-api.exe"))) { throw "missing eq-api.exe" }
New-Item -ItemType Directory -Force -Path $ResApi | Out-Null
Copy-Item -Path (Join-Path $ApiDist "*") -Destination $ResApi -Recurse -Force
Push-Location desktop
if (-not (Test-Path node_modules)) {
    npm install
    Exit-OnNativeFailure "desktop npm install"
}
npm run dist:win
Exit-OnNativeFailure "desktop npm run dist:win"
Pop-Location
Write-Host "DONE see dist-desktop"
Get-ChildItem (Join-Path $Root "dist-desktop") | Format-Table Name, Length, LastWriteTime
