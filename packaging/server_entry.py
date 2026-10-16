"""Entry point of SyncServer.exe (PyInstaller). Same as `python -m syncbridge.server`."""
import sys

from syncbridge.server.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
