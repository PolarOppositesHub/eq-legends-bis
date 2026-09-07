# EQ Legends BiS Windows build
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
Write-Host "app root $Root"
Push-Location frontend
if (-not (Test-Path node_modules)) { npm install }
npm run build
Pop-Location
if (-not (Test-Path .\.venv\Scripts\python.exe)) { py -3 -m venv .venv }
$Vpy = ".\.venv\Scripts\python.exe"
& $Vpy -m pip install -U pip
& $Vpy -m pip install -r backend\requirements.txt pyinstaller
& $Vpy scripts\bundle_desktop_resources.py
& $Vpy -m PyInstaller --noconfirm backend\packaging\eq-api.spec
$ApiDist = Join-Path $Root "dist\eq-api"
$ResApi = Join-Path $Root "desktop\resources\eq-api"
if (-not (Test-Path (Join-Path $ApiDist "eq-api.exe"))) { throw "missing eq-api.exe" }
New-Item -ItemType Directory -Force -Path $ResApi | Out-Null
Copy-Item -Path (Join-Path $ApiDist "*") -Destination $ResApi -Recurse -Force
Push-Location desktop
if (-not (Test-Path node_modules)) { npm install }
npm run dist:win
Pop-Location
Write-Host "DONE see dist-desktop"
Get-ChildItem (Join-Path $Root "dist-desktop") | Format-Table Name, Length, LastWriteTime
