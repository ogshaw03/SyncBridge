"""Phase 1 message protocol between the Sync Server and the Maya / AE clients.

Pure standard library: imported by the server, by the Maya client (inside
Maya's Python) and by tests. Messages are exchange envelopes
(syncbridge.core.envelope) sent as JSON text frames. See docs/API.md.

Session flow:
    client -> server  hello    {token, app, version, pid, document, protocol}
    server -> client  welcome  {client_id, server_version}      (or error + close)
    server -> all     peers    {clients: [...]}                  (whenever it changes)

Manual transfer (docs/PHASE1_PLAN.md 2):
    client -> server  transfer.request {direction, options, target?}
    server -> app     export.request {}           app -> server export.result {export}
    server -> app     apply.request  {apply}       app -> server apply.result  {status, after?, ...}
    server -> client  transfer.result {status, report, readback, ...}
Comp guide (D-16), AE comp frame shown in the Maya view:
    client -> server  guide.request {comp: {name, width, height, pixelAspect}, target?}
    server -> maya    guide.apply.request {guide: comp}   maya -> server guide.apply.result {status, camera, ...}
    server -> client  guide.result {status, camera, render, comp, warnings, source, target}
Key markers (D-18), AE Time Remap key timings as Maya markers:
    client -> server  markers.request {export: ae.timeremap.export envelope, options: {origin, ...}}
    server -> maya    markers.apply.request {export, options}   maya -> server markers.apply.result {status, count, ...}
    server -> client  markers.result {status, count, first, last, bookmarks, source, target}
Scene settings (D-21), FPS / ranges / pixel aspect, either direction, from either panel:
    client -> server  settings.request {direction, items, options: {origin}}
    server -> apps    settings.export.request {}   app -> server settings.export.result {settings}
    server -> target  settings.apply.request {plan, message}   (the user confirms there)
                      target -> server settings.apply.result {status, after?, backup?}
    server -> client  settings.result {status, direction, changes, warnings, readback, ...}
Pixel Mapping (D-23 / D-24), the AE BG layer's position on the mapped Maya camera:
    client -> server  pixelmap.request {info: SBCep.pixelMapInfo(), options: {method?}}
    server -> maya    pixelmap.apply.request {info, options}   maya -> server pixelmap.apply.result {status, ...}
    server -> client  pixelmap.result {status, mapping, values, max_error_px, warnings, source, target}
AE layers for Maya's layer map (D-28):
    maya -> server    layers.request {[main_comp_id, main_comp]}   server -> ae  layers.export.request {same}
    ae -> server      layers.export.result {comp, active, layers}   server -> maya  layers.result {comp, active, layers, ...}
                      (D-40: each layer has `selected`, its selection in the comp open in AE)
    maya -> server    motion.request {comp_id, comp, layer_id, layer, times}  (Phase 3, D-30)
                      server -> ae  motion.export.request (same)
    ae -> server      motion.export.result {comp, layer, samples}   server -> maya  motion.result (same, ...)
Time slider sync (D-22), no replies:
    client -> server  time.sync {enabled, follow_playback}   server -> all  time.sync.state {...}
    client -> server  time.update {t}    server -> the other app  time.set {t, source}
    client -> server  timing.set {origin}   server -> all  timing.state {origin, by}  (one Origin frame, D-38)
    (t = AE comp time in seconds; Maya converts with its origin frame, core.time_sync)
A reply carries `reply_to` = the request's event_id. Failures are `error`
{code, message} with `reply_to` when they answer a request.
"""
from __future__ import annotations

import json
from typing import Optional

from .core import envelope

PROTOCOL_VERSION = 1
DEFAULT_PORT = 8765
HOST = "127.0.0.1"
WS_PATH = "/ws"

APPS = ("maya", "ae", "test")
DIRECTIONS = {"maya2ae": ("maya", "ae"), "ae2maya": ("ae", "maya")}

# error codes
E_BAD_MESSAGE = "bad_message"
E_AUTH = "auth_failed"
E_NO_PEER = "no_peer"
E_TIMEOUT = "timeout"
E_DISCONNECTED = "peer_disconnected"
E_APP = "app_error"
E_CONVERSION = "conversion_failed"
E_BUSY = "busy"
E_REPLACED = "replaced"          # a newer connection from the same process took over
E_HUB_STOPPING = "hub_stopping"  # the hub was stopped from the monitor (P-B)
E_DISCONNECTED_BY_ADMIN = "disconnected_by_admin"   # the monitor disconnected this app (P-A)

# request kind -> reply kind
REPLIES = {
    "transfer.request": "transfer.result",
    "export.request": "export.result",
    "apply.request": "apply.result",
    "guide.request": "guide.result",
    "guide.apply.request": "guide.apply.result",
    "markers.request": "markers.result",
    "markers.apply.request": "markers.apply.result",
    "settings.request": "settings.result",
    "settings.export.request": "settings.export.result",
    "settings.apply.request": "settings.apply.result",
    "pixelmap.request": "pixelmap.result",
    "pixelmap.apply.request": "pixelmap.apply.result",
    "layers.request": "layers.result",
    "layers.export.request": "layers.export.result",
    "motion.request": "motion.result",
    "motion.export.request": "motion.export.result",
}

# required data fields per kind (minimal structural validation)
REQUIRED = {
    "hello": ("token", "app"),
    "welcome": ("client_id",),
    "peers": ("clients",),
    "transfer.request": ("direction",),
    "transfer.result": ("status",),
    "export.request": (),
    "export.result": ("export",),
    "apply.request": ("apply",),
    "apply.result": ("status",),
    "guide.request": ("comp",),
    "guide.result": ("status",),
    "guide.apply.request": ("guide",),
    "guide.apply.result": ("status",),
    "markers.request": ("export",),
    "markers.result": ("status",),
    "markers.apply.request": ("export",),
    "markers.apply.result": ("status",),
    "settings.request": ("direction",),
    "settings.result": ("status",),
    "settings.export.request": (),
    "settings.export.result": ("settings",),
    "settings.apply.request": ("plan",),
    "settings.apply.result": ("status",),
    "pixelmap.request": ("info",),
    "pixelmap.result": ("status",),
    "pixelmap.apply.request": ("info",),
    "pixelmap.apply.result": ("status",),
    "layers.request": (),
    "layers.result": ("layers",),
    "layers.export.request": (),
    "layers.export.result": ("layers",),
    "motion.request": ("times",),
    "motion.result": ("samples",),
    "motion.export.request": ("times",),
    "motion.export.result": ("samples",),
    "time.sync": ("enabled",),
    "time.sync.state": ("enabled",),
    "time.update": ("t",),
    "time.set": ("t",),
    "timing.set": ("origin",),
    "timing.state": ("origin",),
    "error": ("code", "message"),
}

# apply.result / transfer.result status values
APPLIED = "applied"
CANCELLED = "cancelled"
FAILED = "failed"
UNCHANGED = "unchanged"          # settings: the target already has these values
STATUSES = (APPLIED, CANCELLED, FAILED, UNCHANGED)
RESULT_KINDS = ("apply.result", "transfer.result", "guide.result", "guide.apply.result",
                "markers.result", "markers.apply.result", "settings.result", "settings.apply.result",
                "pixelmap.result", "pixelmap.apply.result")
TIME_KINDS = ("time.sync", "time.update", "timing.set")      # client -> server, no reply


class ProtocolError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def message(kind: str, data: Optional[dict] = None, source_id: str = "server",
            reply_to: Optional[str] = None) -> dict:
    return envelope.make(kind, data or {}, source_id, reply_to=reply_to)


def reply(request: dict, data: Optional[dict] = None, source_id: str = "server") -> dict:
    """The reply envelope for `request` (kind from REPLIES)."""
    kind = REPLIES.get(request.get("kind"))
    if kind is None:
        raise ProtocolError(E_BAD_MESSAGE, "%r is not a request" % request.get("kind"))
    return message(kind, data, source_id, reply_to=request["event_id"])


def error(code: str, msg: str, source_id: str = "server", reply_to: Optional[str] = None) -> dict:
    return message("error", {"code": code, "message": msg}, source_id, reply_to)


def describe_result(result: Optional[dict]) -> str:
    """One-line human readable summary of transfer.result data (for logs / UIs)."""
    if not result:
        return "-"
    parts = [result.get("direction", ""), result.get("status", "")]
    conv = (result.get("report") or {}).get("conversion")
    if conv:
        parts.append("conversion %.4f f" % conv["max_error_frames"])
    rb = result.get("readback")
    if rb:
        parts.append("readback %.4f f%s" % (rb["max_error_frames"], "" if rb["passed"] else " FAIL"))
    return " ".join(p for p in parts if p)


def encode(msg: dict) -> str:
    return json.dumps(msg, ensure_ascii=False, separators=(",", ":"))


def decode(text) -> dict:
    """Parse and validate one message; raises ProtocolError."""
    try:
        msg = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ProtocolError(E_BAD_MESSAGE, "not JSON: %s" % exc)
    if not isinstance(msg, dict):
        raise ProtocolError(E_BAD_MESSAGE, "message must be a JSON object")
    try:
        data = envelope.check(msg)
    except ValueError as exc:
        raise ProtocolError(E_BAD_MESSAGE, str(exc))
    kind = msg.get("kind")
    if kind not in REQUIRED:
        raise ProtocolError(E_BAD_MESSAGE, "unexpected kind %r" % kind)
    if not isinstance(data, dict):
        raise ProtocolError(E_BAD_MESSAGE, "data must be an object")
    missing = [f for f in REQUIRED[kind] if f not in data]
    if missing:
        raise ProtocolError(E_BAD_MESSAGE, "%s: missing %s" % (kind, ", ".join(missing)))
    if not isinstance(msg.get("event_id"), str):
        raise ProtocolError(E_BAD_MESSAGE, "event_id must be a string")
    if kind in ("transfer.request", "settings.request") and data["direction"] not in DIRECTIONS:
        raise ProtocolError(E_BAD_MESSAGE, "direction must be one of %s" % sorted(DIRECTIONS))
    if kind in RESULT_KINDS and data["status"] not in STATUSES:
        raise ProtocolError(E_BAD_MESSAGE, "status must be one of %s" % (STATUSES,))
    if kind in ("time.update", "time.set") and not isinstance(data["t"], (int, float)):
        raise ProtocolError(E_BAD_MESSAGE, "t must be a number (seconds)")
    if kind in ("timing.set", "timing.state") and (isinstance(data["origin"], bool)
                                                   or not isinstance(data["origin"], (int, float))):
        raise ProtocolError(E_BAD_MESSAGE, "origin must be a number (Maya frame)")
    if kind == "hello" and data["app"] not in APPS:
        raise ProtocolError(E_BAD_MESSAGE, "app must be one of %s" % (APPS,))
    return msg
