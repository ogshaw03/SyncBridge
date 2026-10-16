"""Entry point of SyncBridge.exe (PyInstaller, windowed). Same as `python -m syncbridge.monitor`.

For now SyncBridge.exe is the monitor only; P-C adds the launcher to the same program
(docs/PLATFORM_DESIGN.md 6).
"""
import sys

from syncbridge.monitor.window import run

if __name__ == "__main__":
    sys.exit(run())
