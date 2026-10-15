"""Session file and single-instance check for the Local Sync Server.

The server writes {port, token, pid, started, version} to
    %LOCALAPPDATA%/SyncBridge/session.json   (Windows)
    ~/.syncbridge/session.json                (elsewhere)
Clients (Maya, AE) read it to find the port and the token they must send in
`hello`. The file lives in the user's profile, so other users and web pages
cannot read the token (SPEC: loopback only, session token).

SYNCBRIDGE_SESSION_DIR overrides the folder (tests, multiple installs).
Standard library only: the Maya client imports this module too.
"""
from __future__ import annotations

import datetime
import json
import os
import secrets
import tempfile
import urllib.error
import urllib.request
from typing import Optional

SESSION_FILE = "session.json"
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


def write_session(port: int, token: str, version: str) -> str:
    """Write the session file atomically and return its path."""
    folder = session_dir()
    os.makedirs(folder, exist_ok=True)
    data = {
        "port": port,
        "token": token,
        "pid": os.getpid(),
        "version": version,
        "started": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    fd, tmp = tempfile.mkstemp(prefix="session.", suffix=".tmp", dir=folder)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, session_path())
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
    """Delete the session file if it belongs to `pid` (default: this process)."""
    pid = os.getpid() if pid is None else pid
    data = read_session()
    if data is not None and data.get("pid") == pid:
        try:
            os.remove(session_path())
        except OSError:
            pass


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
