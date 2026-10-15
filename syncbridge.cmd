@echo off
rem SyncBridge CLI launcher for Windows (no install needed).
rem Usage: syncbridge.cmd <command> [options]   e.g. syncbridge.cmd selftest
rem Uses the Python launcher (py -3) because "python" may be the Microsoft Store stub.
setlocal
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m syncbridge.cli %*
) else (
    python -m syncbridge.cli %*
)
exit /b %errorlevel%
