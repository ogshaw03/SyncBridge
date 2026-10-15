@echo off
rem SyncBridge Local Sync Server (development). Needs the repository venv:
rem   py -3.10 -m venv .venv
rem   .venv\Scripts\python -m pip install -r requirements-server.txt
rem Usage: syncbridge-server.cmd [--port 8765] [--idle-timeout 600]
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo error: .venv not found. Run: py -3.10 -m venv .venv ^&^& .venv\Scripts\python -m pip install -r requirements-server.txt
    exit /b 1
)
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
"%~dp0.venv\Scripts\python.exe" -m syncbridge.server %*
exit /b %errorlevel%
