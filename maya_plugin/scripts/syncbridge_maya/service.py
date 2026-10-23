"""Maya's connection to the SyncBridge Local Sync Server (Phase 1-B).

One SyncClient per Maya session. Server requests are answered on Maya's main
thread through maya.utils.executeDeferred (H-MY-14):

    export.request -> exchange.build_export(allow_missing=True)
    apply.request  -> exchange.apply_envelope(...)   (confirmation dialog, backup, undo, readback)
    guide.apply.request -> comp_guide.show(...)      (AE comp frame in the active view, D-16)
    markers.apply.request -> key_markers.apply(...)  (AE key timings as markers, D-18)
    settings.export.request / settings.apply.request -> scene_settings (FPS, ranges, D-21)
    time.sync.state / time.set -> time_sync (time slider sync, D-22)

    import syncbridge_maya.service as svc
    svc.connect(start_server=True)
    svc.send_to_ae({"origin": 1})        # result is printed and passed to listeners
"""
from __future__ import annotations

from typing import Callable, List, Optional

import maya.utils
from maya import cmds

from syncbridge import protocol
from syncbridge.client import launcher
from syncbridge.client.sync_client import ConnectError, SyncClient
from syncbridge.core import time_sync as core_time_sync

from . import comp_guide, exchange, key_markers, scene_settings
from .time_sync import MayaTimeSync

_client: Optional[SyncClient] = None
_listeners: List[Callable[[str, object], None]] = []
_time_state = {"enabled": False, "follow_playback": False, "by": None}


def _send_time(t: float) -> bool:
    # sent_at: the receiving app measures the delay (same PC, same clock)
    return _client is not None and _client.send("time.update", {"t": t, "sent_at": core_time_sync.now_ms()})


_timesync = MayaTimeSync(_send_time)

# The live client is also remembered in __main__, which survives reloading these
# modules. Reloading (e.g. deleting syncbridge* from sys.modules and importing again)
# used to leave the old connection open and still receiving transfers (V-P1C).
_REGISTRY_KEY = "_syncbridge_maya_client"


def _registered() -> Optional[SyncClient]:
    import __main__
    return getattr(__main__, _REGISTRY_KEY, None)


def _register(client_obj: Optional[SyncClient]) -> None:
    import __main__
    setattr(__main__, _REGISTRY_KEY, client_obj)


def _close_previous() -> None:
    """Disconnect a client left over from an earlier load of this module."""
    old = _registered()
    if old is not None and old is not _client:
        try:
            if old.connected:
                print("SyncBridge: closing the connection of a previous load (%s)" % old.client_id)
                old.disconnect()
        finally:
            _register(None)


def add_listener(fn: Callable[[str, object], None]) -> None:
    """fn(event, payload) on the main thread: client events and "transfer_result"."""
    if fn not in _listeners:
        _listeners.append(fn)


def remove_listener(fn) -> None:
    if fn in _listeners:
        _listeners.remove(fn)


def _notify(event: str, payload) -> None:
    for fn in list(_listeners):
        try:
            fn(event, payload)
        except Exception as exc:  # a broken UI must not break the client
            print("SyncBridge: listener error: %s" % exc)


def _on_event(event: str, payload) -> None:
    if event == "connected":
        print("SyncBridge: connected as %s" % payload.get("client_id"))
    elif event == "disconnected":
        print("SyncBridge: disconnected (%s)" % payload)
        _timesync.stop()
        _time_state.update(enabled=False, by=None)
        _notify("time_sync", dict(_time_state))
    elif event == "error":
        cmds.warning("SyncBridge: %s" % payload.get("message"))
    _notify(event, payload)


def _handle_export(msg: dict) -> dict:
    return {"export": exchange.build_export(allow_missing=True)}


def _handle_apply(msg: dict) -> dict:
    """Apply what the server sends (AE -> Maya), then tell the listeners how it went.

    The requester (AE) gets the transfer.result; Maya's own panel only sees
    this request, so the outcome is reported here ("applied" event).
    """
    apply_env = msg["data"]["apply"]
    try:
        result = exchange.apply_envelope(apply_env, confirm=True, origin="After Effects")
    except Exception as exc:
        _notify("applied", {"status": "failed", "message": str(exc)})
        raise
    _notify("applied", {"status": result["status"], "keys": len(apply_env["data"]["native"]["keys"]),
                        "readback": result.get("app_readback"), "backup": result.get("backup")})
    return result


def _handle_guide(msg: dict) -> dict:
    """Show the AE comp's frame in the active view; the panel hears about it ("guide" event)."""
    guide = dict(msg["data"]["guide"])
    guide["name"] = ("AE %s" % guide.get("name", "")).strip()     # the label says it came from AE
    try:
        result = comp_guide.show(guide)
    except Exception as exc:
        _notify("guide", {"status": "failed", "message": str(exc)})
        raise
    _notify("guide", dict(result, name=msg["data"]["guide"].get("name")))
    return result


def _handle_markers(msg: dict) -> dict:
    """Store AE's Time Remap key timings as markers; the panel hears about it ("markers" event)."""
    try:
        result = key_markers.apply(msg["data"]["export"], msg["data"].get("options"))
    except Exception as exc:
        _notify("markers", {"status": "failed", "message": str(exc)})
        raise
    _notify("markers", result)
    return result


def _handle_settings_export(msg: dict) -> dict:
    return {"settings": scene_settings.read()}


def _handle_settings_apply(msg: dict) -> dict:
    """Change the scene settings as the hub planned (after the user confirms); the panel hears about it."""
    data = msg["data"]
    try:
        result = scene_settings.apply(data["plan"], data.get("message") or "")
    except Exception as exc:
        _notify("settings_applied", {"status": "failed", "message": str(exc)})
        raise
    _notify("settings_applied", dict(result, changes=data["plan"].get("changes", [])))
    return result


def _on_time_state(msg: dict) -> None:
    data = msg["data"]
    _time_state.update(enabled=bool(data["enabled"]), follow_playback=bool(data.get("follow_playback")),
                       by=data.get("by"))
    _timesync.set_state(_time_state["enabled"], _time_state["follow_playback"])
    _notify("time_sync", dict(_time_state))
    if not _time_state["enabled"] and _timesync.last_summary:
        _notify("time_sync_stats", _timesync.last_summary)
        _timesync.last_summary = ""


def _on_time_set(msg: dict) -> None:
    _timesync.apply_time(float(msg["data"]["t"]), msg["data"].get("sent_at"))


def client() -> Optional[SyncClient]:
    return _client


def is_connected() -> bool:
    return _client is not None and _client.connected


def connect(start_server: bool = True, port: Optional[int] = None) -> dict:
    """Connect to the server (starting it first if asked). Returns the welcome data."""
    global _client
    if is_connected():
        return {"client_id": _client.client_id}
    _close_previous()
    info = {}
    if start_server:
        # The hub may run on another port when 8765 is taken; the result says which.
        info = launcher.ensure_server(port or protocol.DEFAULT_PORT)
        if info.get("note"):
            print("SyncBridge: %s" % info["note"])
        port = port or info.get("port")
    _client = SyncClient(
        "maya",
        handlers={"export.request": _handle_export, "apply.request": _handle_apply,
                  "guide.apply.request": _handle_guide, "markers.apply.request": _handle_markers,
                  "settings.export.request": _handle_settings_export,
                  "settings.apply.request": _handle_settings_apply},
        notices={"time.sync.state": _on_time_state, "time.set": _on_time_set},
        dispatch=maya.utils.executeDeferred,
        on_event=_on_event,
        version=cmds.about(version=True),
        document=lambda: cmds.file(q=True, sn=True) or "untitled",
    )
    welcome = _client.connect(port=port)
    _register(_client)
    if info.get("note"):
        welcome = dict(welcome, note=info["note"])
    return welcome


def disconnect() -> None:
    if _client is not None:
        _client.disconnect()
    if _registered() is _client:
        _register(None)


def peers() -> list:
    return list(_client.peers) if _client is not None else []


def _transfer(direction: str, options: Optional[dict], callback=None) -> str:
    if not is_connected():
        raise ConnectError("not connected to the SyncBridge server")

    def done(reply: dict) -> None:
        if reply["kind"] == "error":
            cmds.warning("SyncBridge: %s failed: %s" % (direction, reply["data"].get("message")))
        else:
            data = reply["data"]
            print("SyncBridge: %s" % protocol.describe_result(data))
            if data.get("message"):
                print("SyncBridge: %s" % data["message"])
            for w in (data.get("report") or {}).get("warnings", []):
                cmds.warning("SyncBridge: " + w)
        _notify("transfer_result", reply)
        if callback:
            callback(reply)

    return _client.request_transfer(direction, options, done)


def send_to_ae(options: Optional[dict] = None, callback=None) -> str:
    """Maya -> AE: the selected layer in the active AE comp receives the Time Remap."""
    return _transfer("maya2ae", options, callback)


def receive_from_ae(options: Optional[dict] = None, callback=None) -> str:
    """AE -> Maya: the selected AE layer's Time Remap replaces the Scene Time Warp."""
    return _transfer("ae2maya", options, callback)


def send_settings(direction: str, items: List[str], origin: float, callback=None) -> str:
    """Scene settings Maya -> AE ("maya2ae") or AE -> Maya ("ae2maya"); the target app confirms."""
    if not is_connected():
        raise ConnectError("not connected to the SyncBridge server")

    def done(reply: dict) -> None:
        if reply["kind"] == "error":
            cmds.warning("SyncBridge: settings %s failed: %s" % (direction, reply["data"].get("message")))
        else:
            print("SyncBridge: settings %s %s" % (direction, reply["data"].get("status")))
        _notify("settings_result", reply)
        if callback:
            callback(reply)

    return _client.request("settings.request", {"direction": direction, "items": list(items),
                                                "options": {"origin": origin}}, done)


def time_sync_state() -> dict:
    return dict(_time_state)


def set_time_origin(origin: float) -> None:
    """The Origin frame used to convert Maya frames to AE comp time (the panel's field)."""
    _timesync.origin = float(origin)


def set_time_sync(enabled: bool, follow_playback: bool = False, lead: bool = True) -> None:
    """Switch the shared time slider sync; when switching it on, Maya's time leads (lead=True)."""
    if not is_connected():
        raise ConnectError("not connected to the SyncBridge server")
    _client.send("time.sync", {"enabled": bool(enabled), "follow_playback": bool(follow_playback)})
    if enabled and lead:
        _timesync.push_current()


# A reload of this module must not leave the previous connection behind.
_close_previous()
