"""Find running SyncBridge hubs, talk to their admin API, and force-stop a stuck one
(D-15, docs/PLATFORM_DESIGN.md 5). Used by the monitor (P-B); standard library only.

Where hubs come from:
    hubs/<pid>.json     written by every hub since P-A (port, token, pid, executable, started)
    session.json        the hub clients use (0.1.x hubs write only this one)
    process scan        SyncServer.exe processes that left no file (Windows only)

A pid in a file can belong to another program after a crash and a reboot, so a hub is
only "verified" when the process image is SyncServer.exe or the executable recorded in
its file, and the process was created shortly before the file says the hub started.
force_kill() refuses anything that is not verified.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from typing import List, Optional

from .server import session

SERVER_IMAGE = "syncserver.exe"
START_SLACK_S = 300.0        # process creation -> hub file "started"

RUNNING = "running"                  # answers /health
NOT_RESPONDING = "not_responding"    # process alive, no answer
STALE = "stale"                      # file left behind, no process
UNKNOWN = "unknown"                  # SyncServer.exe without a file (no port, no token)


class HubInfo:
    def __init__(self, pid: int, port: Optional[int] = None, token: Optional[str] = None,
                 version: Optional[str] = None, started: Optional[str] = None,
                 executable: Optional[str] = None, file: Optional[str] = None,
                 recorded_image: Optional[str] = None):
        self.pid = pid
        self.port = port
        self.token = token
        self.version = version
        self.started = started
        self.executable = executable
        self.file = file
        self.recorded_image = recorded_image   # the image the hub saw for itself
        self.alive = False
        self.image: Optional[str] = None
        self.verified = False
        self.health: Optional[dict] = None
        self.current = False          # the hub session.json points at
        self.state = STALE

    def to_json(self) -> dict:
        """Everything except the token."""
        return {"pid": self.pid, "port": self.port, "version": self.version, "started": self.started,
                "executable": self.executable, "file": self.file, "alive": self.alive,
                "image": self.image, "verified": self.verified, "current": self.current,
                "state": self.state, "clients": (self.health or {}).get("clients")}

    def __repr__(self):
        return "HubInfo(pid=%d, port=%s, state=%s)" % (self.pid, self.port, self.state)


def discover(health_timeout: float = 0.5, scan_processes: bool = True) -> List[HubInfo]:
    hubs = {}
    for data in session.read_hub_files():
        hubs[data["pid"]] = _from_file(data, data.get("file"))
    current = session.read_session()
    if current and isinstance(current.get("pid"), int):
        pid = current["pid"]
        if pid not in hubs:
            hubs[pid] = _from_file(current, session.session_path())
        hubs[pid].current = True
    if scan_processes:
        for pid in list_server_processes():
            if pid not in hubs:
                hubs[pid] = HubInfo(pid)
    for hub in hubs.values():
        _inspect(hub, health_timeout)
    return sorted(hubs.values(), key=lambda h: (not h.current, h.pid))


def _from_file(data: dict, path: Optional[str]) -> HubInfo:
    return HubInfo(data["pid"], data.get("port"), data.get("token"), data.get("version"),
                   data.get("started"), data.get("executable"), path, data.get("image"))


def _inspect(hub: HubInfo, health_timeout: float) -> None:
    hub.alive = pid_alive(hub.pid)
    hub.image = process_image(hub.pid) if hub.alive else None
    hub.verified = hub.alive and verify(hub)
    if hub.alive and hub.port:
        hub.health = session.probe_server(hub.port, timeout=health_timeout)
    if not hub.alive:
        hub.state = STALE
    elif hub.port is None:
        hub.state = UNKNOWN
    elif hub.health is not None and hub.verified:
        hub.state = RUNNING
    else:
        hub.state = NOT_RESPONDING


def verify(hub: HubInfo) -> bool:
    """Is process `hub.pid` really this SyncBridge hub (not a reused pid)?"""
    image = process_image(hub.pid)
    if not image:
        return False
    norm = os.path.normcase(os.path.abspath(image))
    is_server = os.path.basename(norm) == SERVER_IMAGE
    if not is_server:
        recorded = [os.path.normcase(os.path.abspath(p)) for p in (hub.recorded_image, hub.executable) if p]
        if norm not in recorded:
            return False
    if hub.started:                  # pid reuse: the process must be older than the hub file, but not by much
        created = process_create_time(hub.pid)
        started = _parse_iso(hub.started)
        if created is not None and started is not None:
            gap = started - created
            if gap < -5.0 or gap > START_SLACK_S:
                return False
    elif not is_server:
        return False
    return True


def force_kill(hub: HubInfo) -> None:
    """Terminate the hub process. Raises ValueError unless it is a verified SyncBridge hub."""
    hub.image = process_image(hub.pid)
    if not pid_alive(hub.pid) or not verify(hub):
        raise ValueError("process %d is not a SyncBridge hub; not stopping it" % hub.pid)
    _terminate(hub.pid)
    session.remove_session(hub.pid)


def remove_stale(hub: HubInfo) -> bool:
    """Delete the files of a hub whose process is gone. Returns False if it is still running."""
    if pid_alive(hub.pid):
        return False
    session.remove_session(hub.pid)
    return True


# ---- admin API -------------------------------------------------------------------------

class AdminError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__("%s %s" % (status, message))
        self.status = status
        self.message = message


def admin_call(hub: HubInfo, method: str, path: str, timeout: float = 3.0):
    """GET/POST http://127.0.0.1:<port>/admin/<path> with the hub's token; return the JSON."""
    if not hub.port or not hub.token:
        raise AdminError(0, "no port or token for hub %d" % hub.pid)
    req = urllib.request.Request("http://127.0.0.1:%d/admin/%s" % (hub.port, path.lstrip("/")),
                                 method=method, data=b"" if method == "POST" else None,
                                 headers={"Authorization": "Bearer " + hub.token})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise AdminError(exc.code, exc.reason)
    except (OSError, ValueError) as exc:
        raise AdminError(0, str(exc))


# ---- processes -------------------------------------------------------------------------

def _parse_iso(text: str) -> Optional[float]:
    try:
        return datetime.datetime.fromisoformat(text).timestamp()
    except (TypeError, ValueError):
        return None


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
    _k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    _k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _k32.K32EnumProcesses.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD,
                                      ctypes.POINTER(wintypes.DWORD)]

    _QUERY_LIMITED = 0x1000
    _TERMINATE = 0x0001
    _STILL_ACTIVE = 259
    _EPOCH_DIFF_100NS = 116444736000000000      # 1601-01-01 -> 1970-01-01

    def _open(pid: int, access: int = _QUERY_LIMITED):
        if pid <= 0:
            return None
        return _k32.OpenProcess(access, False, pid) or None

    def pid_alive(pid: int) -> bool:
        h = _open(pid)
        if not h:
            return False
        try:
            code = wintypes.DWORD()
            return bool(_k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == _STILL_ACTIVE
        finally:
            _k32.CloseHandle(h)

    def process_image(pid: int) -> Optional[str]:
        h = _open(pid)
        if not h:
            return None
        try:
            buf = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buf))
            if _k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return buf.value
            return None
        finally:
            _k32.CloseHandle(h)

    def process_create_time(pid: int) -> Optional[float]:
        h = _open(pid)
        if not h:
            return None
        try:
            t = [wintypes.FILETIME() for _ in range(4)]
            if not _k32.GetProcessTimes(h, *[ctypes.byref(x) for x in t]):
                return None
            ticks = (t[0].dwHighDateTime << 32) | t[0].dwLowDateTime
            return (ticks - _EPOCH_DIFF_100NS) / 1e7
        finally:
            _k32.CloseHandle(h)

    def list_server_processes() -> List[int]:
        arr = (wintypes.DWORD * 4096)()
        needed = wintypes.DWORD()
        if not _k32.K32EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(needed)):
            return []
        pids = []
        for pid in arr[:needed.value // ctypes.sizeof(wintypes.DWORD)]:
            image = process_image(pid)
            if image and os.path.basename(image).lower() == SERVER_IMAGE:
                pids.append(int(pid))
        return pids

    def _terminate(pid: int) -> None:
        h = _open(pid, _TERMINATE | _QUERY_LIMITED)
        if not h:
            raise OSError("cannot open process %d" % pid)
        try:
            if not _k32.TerminateProcess(h, 1):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            _k32.CloseHandle(h)

else:  # development on other systems; the product targets Windows
    import signal

    def pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def process_image(pid: int) -> Optional[str]:
        try:
            return os.readlink("/proc/%d/exe" % pid)
        except OSError:
            return None

    def process_create_time(pid: int) -> Optional[float]:
        return None

    def list_server_processes() -> List[int]:
        return []

    def _terminate(pid: int) -> None:
        os.kill(pid, signal.SIGTERM)


__all__ = ["HubInfo", "discover", "verify", "force_kill", "remove_stale", "admin_call", "AdminError",
           "pid_alive", "process_image", "process_create_time", "list_server_processes",
           "RUNNING", "NOT_RESPONDING", "STALE", "UNKNOWN"]
