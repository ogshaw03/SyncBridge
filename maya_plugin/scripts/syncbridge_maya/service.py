"""Maya's connection to the SyncBridge Local Sync Server (Phase 1-B).

One SyncClient per Maya session. Server requests are answered on Maya's main
thread through maya.utils.executeDeferred (H-MY-14):

    export.request -> exchange.build_export(allow_missing=True)
    apply.request  -> exchange.apply_envelope(...)   (confirmation dialog, backup, undo, readback)

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

from . import exchange

_client: Optional[SyncClient] = None
_listeners: List[Callable[[str, object], None]] = []


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


def client() -> Optional[SyncClient]:
    return _client


def is_connected() -> bool:
    return _client is not None and _client.connected


def connect(start_server: bool = True, port: Optional[int] = None) -> dict:
    """Connect to the server (starting it first if asked). Returns the welcome data."""
    global _client
    if is_connected():
        return {"client_id": _client.client_id}
    if start_server:
        launcher.ensure_server(port or protocol.DEFAULT_PORT)
    _client = SyncClient(
        "maya",
        handlers={"export.request": _handle_export, "apply.request": _handle_apply},
        dispatch=maya.utils.executeDeferred,
        on_event=_on_event,
        version=cmds.about(version=True),
        document=lambda: cmds.file(q=True, sn=True) or "untitled",
    )
    return _client.connect(port=port)


def disconnect() -> None:
    if _client is not None:
        _client.disconnect()


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
