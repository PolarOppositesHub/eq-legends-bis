# Build FastAPI sidecar on Windows (PyInstaller one-folder).
# Run from repo root in PowerShell: .\scriptsuild_api_sidecar.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
  python -m venv .venv
  $py = Join-Path $Root ".venv\Scripts\python.exe"
}
& $py -m pip install -U pip
& $py -m pip install -r backendequirements.txt pyinstaller

$env:PYTHONPATH = "$Root;$Rootackend;$Rootackendendor"
Set-Location (Join-Path $Root "packaging")
& $py -m PyInstaller --noconfirm eq-api.spec

$out = Join-Path $Root "packaging\dist\eq-api"
$dest = Join-Path $Root "resourcespi"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item -Recurse -Force "$out\*" $dest
Write-Host "Sidecar copied to $dest"
Get-ChildItem $dest | Select-Object Name, Length
