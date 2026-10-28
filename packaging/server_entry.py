"""Entry point of SyncServer.exe (PyInstaller). Same as `python -m syncbridge.server`;
`SyncServer.exe update ...` is the updater's command line instead (`python -m syncbridge.updater`, D-46)."""
import sys

if __name__ == "__main__":
    if sys.argv[1:2] == ["update"]:
        from syncbridge.updater.__main__ import main as update_main
        sys.exit(update_main(sys.argv[2:]))
    from syncbridge.server.__main__ import main
    sys.exit(main())
