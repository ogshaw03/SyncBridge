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

# request kind -> reply kind
REPLIES = {
    "transfer.request": "transfer.result",
    "export.request": "export.result",
    "apply.request": "apply.result",
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
    "error": ("code", "message"),
}

# apply.result / transfer.result status values
APPLIED = "applied"
CANCELLED = "cancelled"
FAILED = "failed"
STATUSES = (APPLIED, CANCELLED, FAILED)


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
    if kind == "transfer.request" and data["direction"] not in DIRECTIONS:
        raise ProtocolError(E_BAD_MESSAGE, "direction must be one of %s" % sorted(DIRECTIONS))
    if kind in ("apply.result", "transfer.result") and data["status"] not in STATUSES:
        raise ProtocolError(E_BAD_MESSAGE, "status must be one of %s" % (STATUSES,))
    if kind == "hello" and data["app"] not in APPS:
        raise ProtocolError(E_BAD_MESSAGE, "app must be one of %s" % (APPS,))
    return msg
