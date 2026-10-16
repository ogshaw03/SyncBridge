@echo off
rem SyncBridge monitor (development). Needs the repository venv with the monitor packages:
rem   .venv\Scripts\python -m pip install -r requirements-server.txt -r requirements-monitor.txt
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo error: .venv not found. Run: py -3.10 -m venv .venv ^&^& .venv\Scripts\python -m pip install -r requirements-server.txt -r requirements-monitor.txt
    exit /b 1
)
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
"%~dp0.venv\Scripts\python.exe" -m syncbridge.monitor %*
exit /b %errorlevel%
