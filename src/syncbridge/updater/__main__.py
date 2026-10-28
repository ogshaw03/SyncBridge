"""Command line of the updater, for the After Effects panel (D-46, TEMPORARY): JSON lines on stdout.

    SyncServer.exe update list                -> {"current": "0.1.15", "releases": [...]}
    SyncServer.exe update install v0.1.9      -> {"progress": [done, total]} ... {"launching": "exe"} {"done": "exe"}
    python -m syncbridge.updater list         (development: the repository's .venv)

Errors: {"error": "<Japanese message>"} and exit code 1. "launching" comes before the installer starts:
the zip's Install.bat stops SyncServer.exe processes of the install folder, maybe this one.
"""
from __future__ import annotations

import json
import sys
from typing import List, Optional

from .. import __version__
from . import install, releases


def _say(obj) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if args[:1] == ["list"]:
            _say({"current": __version__, "page": releases.PAGE_URL, "releases": releases.releases(__version__)})
            return 0
        if args[:1] == ["install"] and len(args) == 2:
            found = [r for r in releases.releases(__version__) if r["tag"] == args[1]]
            if not found:
                raise RuntimeError(u"GitHub に %s のリリースが見つかりません。" % args[1])
            if not found[0]["asset"]:
                raise RuntimeError(u"%s には、SyncBridge のインストーラーも zip もありません。" % args[1])
            last = [0]

            def progress(done, total):
                if done - last[0] >= 1024 * 1024 or done == total:
                    last[0] = done
                    _say({"progress": [done, total]})
            path = install.download(found[0]["asset"], progress=progress)
            kind = "exe" if path.lower().endswith(".exe") else "zip"
            _say({"launching": kind, "path": path})
            install.launch(path)
            _say({"done": kind})
            return 0
        _say({"error": "usage: update list | update install <tag>"})
        return 2
    except Exception as exc:
        _say({"error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
