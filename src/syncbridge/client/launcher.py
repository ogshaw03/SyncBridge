"""Start the Local Sync Server from an application (development layout).

Development: <repo>/.venv python runs `-m syncbridge.server` with <repo>/src
on PYTHONPATH. Phase 6 replaces this with SyncServer.exe.

The child must not inherit the host application's Python settings: Maya sets
PYTHONHOME / PYTHONPATH for its own interpreter, which would make the venv
python import Maya's packages (H-MY-15). They are removed from the child's
environment.
"""
from __future__ import annotations

import os
import subprocess
import time
from typing import Optional

from .. import protocol
from ..server import session

_children = []

# Variables of the parent interpreter that must not leak into the server process.
STRIP_ENV = ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONNOUSERSITE",
             "PYTHONEXECUTABLE", "__PYVENV_LAUNCHER__")


def repo_root() -> str:
    # <repo>/src/syncbridge/client/launcher.py
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))


def venv_python(root: Optional[str] = None) -> str:
    root = root or repo_root()
    if os.name == "nt":
        return os.path.join(root, ".venv", "Scripts", "python.exe")
    return os.path.join(root, ".venv", "bin", "python")


def server_env(base: Optional[dict] = None, root: Optional[str] = None) -> dict:
    env = dict(os.environ if base is None else base)
    for name in STRIP_ENV:
        env.pop(name, None)
    env["PYTHONPATH"] = os.path.join(root or repo_root(), "src")
    return env


def ensure_server(port: int = protocol.DEFAULT_PORT, python: Optional[str] = None,
                  idle_timeout: float = 600.0, wait: float = 15.0) -> dict:
    """Return the running server's /health info, starting the server first if needed.

    Raises RuntimeError when it cannot be started (no venv, port taken, timeout).
    """
    info = session.probe_server(port)
    if info:
        return info
    if session.port_in_use(port):
        raise RuntimeError("port %d is used by another program" % port)
    python = python or venv_python()
    if not os.path.isfile(python):
        raise RuntimeError("server python not found: %s (create the .venv, see CLAUDE.md)" % python)
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
        [python, "-m", "syncbridge.server", "--port", str(port), "--idle-timeout", str(idle_timeout)],
        env=server_env(), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
        close_fds=True, cwd=repo_root(), **kwargs))
    log.close()
    deadline = time.time() + wait
    while time.time() < deadline:
        info = session.probe_server(port, timeout=0.5)
        if info and session.read_session():
            return info
        time.sleep(0.2)
    raise RuntimeError("the server did not start within %g s (see %s)"
                       % (wait, os.path.join(log_dir, "server.log")))


__all__ = ["ensure_server", "repo_root", "server_env", "venv_python"]
