@echo off
setlocal
cd /d "%~dp0.."
echo Running build-windows.ps1 from %CD%
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-windows.ps1"
if errorlevel 1 exit /b 1
echo BUILD OK - see dist-desktop
endlocal
