@echo off
rem SyncBridge uninstaller. Double-click this file (in the SyncBridge install folder or the release folder).
if exist "%~dp0uninstall.ps1" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0payload\uninstall.ps1"
)
exit /b %errorlevel%
