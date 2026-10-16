"""Session file and single-instance check for the Local Sync Server.

The server writes {port, token, pid, started, version} to
    %LOCALAPPDATA%/SyncBridge/session.json   (Windows)
    ~/.syncbridge/session.json                (elsewhere)
Clients (Maya, AE) read it to find the port and the token they must send in
`hello`. The file lives in the user's profile, so other users and web pages
cannot read the token (SPEC: loopback only, session token).

Each running hub also writes hubs/<pid>.json with the same content plus its
executable (D-15, docs/PLATFORM_DESIGN.md 4.4): several hubs can run at once
(development and installed, a left-over after a crash), and the monitor finds
them there. session.json keeps pointing at the hub clients should use.

SYNCBRIDGE_SESSION_DIR overrides the folder (tests, multiple installs).
Standard library only: the Maya client imports this module too.
"""
from __future__ import annotations

import datetime
import json
import os
import glob
import secrets
import sys
import tempfile
import urllib.error
import urllib.request
from typing import List, Optional

SESSION_FILE = "session.json"
HUBS_DIR = "hubs"
ENV_DIR = "SYNCBRIDGE_SESSION_DIR"


def session_dir() -> str:
    override = os.environ.get(ENV_DIR)
    if override:
        return override
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return os.path.join(base, "SyncBridge")
    return os.path.join(os.path.expanduser("~"), ".syncbridge")


def session_path() -> str:
    return os.path.join(session_dir(), SESSION_FILE)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hubs_dir() -> str:
    return os.path.join(session_dir(), HUBS_DIR)


def hub_path(pid: int) -> str:
    return os.path.join(hubs_dir(), "%d.json" % pid)


def _write_json_atomic(path: str, data: dict) -> None:
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="session.", suffix=".tmp", dir=folder)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def _own_image() -> Optional[str]:
    try:
        from .. import hubs        # late: hubs imports this module
        return hubs.process_image(os.getpid())
    except Exception:
        return None


def write_session(port: int, token: str, version: str) -> str:
    """Write session.json and hubs/<pid>.json atomically; return the session.json path."""
    data = {
        "port": port,
        "token": token,
        "pid": os.getpid(),
        "version": version,
        "started": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "executable": sys.executable,
        # The real process image: in a venv on Windows sys.executable is a launcher that
        # starts the base python as a child, so the hub runs under another file.
        "image": _own_image(),
    }
    _write_json_atomic(hub_path(os.getpid()), data)
    _write_json_atomic(session_path(), data)
    return session_path()


def read_session() -> Optional[dict]:
    try:
        with open(session_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or "port" not in data or "token" not in data:
        return None
    return data


def remove_session(pid: Optional[int] = None) -> None:
    """Delete hubs/<pid>.json, and session.json if it belongs to `pid` (default: this process)."""
    pid = os.getpid() if pid is None else pid
    remove_hub_file(pid)
    data = read_session()
    if data is not None and data.get("pid") == pid:
        try:
            os.remove(session_path())
        except OSError:
            pass


def remove_hub_file(pid: int) -> None:
    try:
        os.remove(hub_path(pid))
    except OSError:
        pass


def read_hub_files() -> List[dict]:
    """All hubs/*.json (a hub that crashed leaves its file behind; see syncbridge.hubs)."""
    hubs = []
    for path in sorted(glob.glob(os.path.join(hubs_dir(), "*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get("pid"), int) and "port" in data:
            data["file"] = path
            hubs.append(data)
    return hubs


def probe_server(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> Optional[dict]:
    """Return the /health answer if a SyncBridge server is listening on `port`, else None."""
    try:
        with urllib.request.urlopen("http://%s:%d/health" % (host, port), timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return None
    if isinstance(data, dict) and data.get("app") == "syncbridge":
        return data
    return None


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0
