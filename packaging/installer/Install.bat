@echo off
rem SyncBridge installer. Double-click this file.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0payload\install.ps1"
exit /b %errorlevel%
