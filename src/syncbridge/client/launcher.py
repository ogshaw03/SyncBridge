"""Start the Local Sync Server from an application.

Where the server comes from, first match wins (server_command):
  1. SYNCBRIDGE_SERVER_EXE environment variable (a SyncServer.exe path)
  2. installed release: <install root>/server/SyncServer.exe, where this file is
     <install root>/maya/scripts/syncbridge/client/launcher.py
  3. the default install folder %LOCALAPPDATA%/Programs/SyncBridge/server/SyncServer.exe
  4. development: <repo>/.venv python with `-m syncbridge.server` and <repo>/src on PYTHONPATH

The child must not inherit the host application's Python settings: Maya sets
PYTHONHOME / PYTHONPATH for its own interpreter, which would make the venv
python import Maya's packages (H-MY-15). They are removed from the child's
environment.
"""
from __future__ import annotations

import os
import subprocess
import time
from typing import List, Optional, Tuple

from .. import protocol
from ..server import session

_children = []

SERVER_EXE = "SyncServer.exe"
ENV_SERVER_EXE = "SYNCBRIDGE_SERVER_EXE"

# Variables of the parent interpreter that must not leak into the server process.
STRIP_ENV = ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONNOUSERSITE",
             "PYTHONEXECUTABLE", "__PYVENV_LAUNCHER__")


def _here() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def repo_root() -> str:
    # development: <repo>/src/syncbridge/client/launcher.py
    return os.path.normpath(os.path.join(_here(), "..", "..", ".."))


def install_root() -> str:
    # release: <install root>/maya/scripts/syncbridge/client/launcher.py
    return os.path.normpath(os.path.join(_here(), "..", "..", "..", ".."))


def default_install_root() -> Optional[str]:
    base = os.environ.get("LOCALAPPDATA")
    return os.path.join(base, "Programs", "SyncBridge") if base else None


def venv_python(root: Optional[str] = None) -> str:
    root = root or repo_root()
    if os.name == "nt":
        return os.path.join(root, ".venv", "Scripts", "python.exe")
    return os.path.join(root, ".venv", "bin", "python")


def server_env(base: Optional[dict] = None, root: Optional[str] = None) -> dict:
    env = dict(os.environ if base is None else base)
    for name in STRIP_ENV:
        env.pop(name, None)
    if root is not None:
        env["PYTHONPATH"] = os.path.join(root, "src")
    return env


def server_command(python: Optional[str] = None) -> Tuple[List[str], dict, str]:
    """(argv prefix, environment, working folder) of the server to start.

    `python` forces the development form with that interpreter (tests).
    Raises RuntimeError when no server can be found.
    """
    if python is None:
        candidates = [os.environ.get(ENV_SERVER_EXE),
                      os.path.join(install_root(), "server", SERVER_EXE)]
        default_root = default_install_root()
        if default_root:
            candidates.append(os.path.join(default_root, "server", SERVER_EXE))
        for exe in candidates:
            if exe and os.path.isfile(exe):
                return [exe], server_env(), os.path.dirname(exe)
        python = venv_python()
        if not os.path.isfile(python):
            raise RuntimeError("SyncBridge server not found. Run Install.bat of the SyncBridge "
                               "release again (looked for %s and %s)." % (candidates[1], python))
    if not os.path.isfile(python):
        raise RuntimeError("server python not found: %s" % python)
    root = repo_root()
    return [python, "-m", "syncbridge.server"], server_env(root=root), root


PORT_TRIES = 10       # 8765 ... 8774


def find_running(port: int = protocol.DEFAULT_PORT) -> Optional[dict]:
    """/health of a running SyncBridge hub (+ "port"): the one in session.json, else on `port`."""
    current = session.read_session()
    if current and isinstance(current.get("port"), int):
        info = session.probe_server(current["port"])
        if info:
            return dict(info, port=current["port"])
    info = session.probe_server(port)
    return dict(info, port=port) if info else None


def _owner_text(port: int) -> str:
    try:
        from .. import hubs
        owner = hubs.port_owner(port)
    except Exception:
        owner = None
    if not owner:
        return u"ほかのプログラム"
    return u"ほかのプログラム（%s、PID %d）" % (owner.get("name") or u"名前不明", owner["pid"])


def ensure_server(port: int = protocol.DEFAULT_PORT, python: Optional[str] = None,
                  idle_timeout: float = 600.0, wait: float = 20.0) -> dict:
    """Return the running server's /health info (+ "port", the port it listens on), starting
    the server first if needed.

    When `port` is used by another program, the next free port of PORT_TRIES is used (the
    clients read the port from session.json) and the result has a Japanese "note" saying so.
    Raises RuntimeError when it cannot be started (not installed, no free port, timeout).
    """
    running = find_running(port)
    if running:
        return running
    chosen = None
    busy = []
    for candidate in range(port, port + PORT_TRIES):
        if not session.port_in_use(candidate):
            chosen = candidate
            break
        info = session.probe_server(candidate)
        if info:                                   # a SyncBridge hub whose session file is gone
            return dict(info, port=candidate)
        busy.append(candidate)
    if chosen is None:
        raise RuntimeError(u"SyncBridge のサーバーを起動できません。ポート %d〜%d がすべて使われています"
                           u"（%d は%sが使用中）。" % (port, port + PORT_TRIES - 1, port, _owner_text(port)))
    note = None
    if busy:
        note = (u"ポート %d は%sが使っているため、ポート %d で SyncBridge のサーバーを起動しました。"
                % (busy[0], _owner_text(busy[0]), chosen))
    info = _start(chosen, python, idle_timeout, wait)
    return dict(info, port=chosen, note=note) if note else dict(info, port=chosen)


def _start(port: int, python: Optional[str], idle_timeout: float, wait: float) -> dict:
    argv, env, cwd = server_command(python)
    log_dir = session.session_dir()
    os.makedirs(log_dir, exist_ok=True)
    log = open(os.path.join(log_dir, "server.log"), "a", encoding="utf-8")
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                                   | subprocess.CREATE_NO_WINDOW)
    else:
        kwargs["start_new_session"] = True
    # Detached on purpose: the server outlives this call and stops itself when idle.
    # The handle is kept so it is not reported as a leaked running subprocess.
    _children.append(subprocess.Popen(
        argv + ["--port", str(port), "--idle-timeout", str(idle_timeout)],
        env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
        close_fds=True, cwd=cwd, **kwargs))
    log.close()
    deadline = time.time() + wait
    while time.time() < deadline:
        info = session.probe_server(port, timeout=0.5)
        current = session.read_session()
        if info and current and current.get("port") == port:     # clients read the port from here
            return info
        time.sleep(0.2)
    raise RuntimeError("the server did not start within %g s (see %s)"
                       % (wait, os.path.join(log_dir, "server.log")))


__all__ = ["ensure_server", "find_running", "install_root", "repo_root", "server_command", "server_env",
           "venv_python", "PORT_TRIES"]
