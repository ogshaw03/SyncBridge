"""Exchange envelope shared by file transfer (Phase 0) and WebSocket messages (Phase 1+).

See schemas/envelope.schema.json and docs/API.md.
"""
from __future__ import annotations

import datetime
import json
import uuid
from typing import Optional

SCHEMA = "syncbridge.exchange"
SCHEMA_VERSION = "0.1"

KINDS = (
    "maya.timewarp.export",
    "maya.timewarp.apply",
    "ae.timeremap.export",
    "ae.timeremap.apply",
    "ae.probe.vectors",
    "ae.probe.results",
    "maya.probe.results",
    # Phase 1 messages (syncbridge.protocol, docs/API.md)
    "hello",
    "welcome",
    "peers",
    "transfer.request",
    "transfer.result",
    "export.request",
    "export.result",
    "apply.request",
    "apply.result",
    "error",
)


def make(kind: str, data: dict, source_id: str = "core", app: Optional[dict] = None,
         revision: int = 0, reply_to: Optional[str] = None) -> dict:
    """Build an envelope. `reply_to` is the event_id of the request this answers."""
    if kind not in KINDS:
        raise ValueError("unknown kind: %r" % kind)
    env = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "event_id": str(uuid.uuid4()),
        "source_id": source_id,
        "revision": revision,
        "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "app": app or {},
        "data": data,
    }
    if reply_to is not None:
        env["reply_to"] = reply_to
    return env


def check(envelope: dict, kind: Optional[str] = None) -> dict:
    """Validate the envelope header and return its data."""
    if envelope.get("schema") != SCHEMA:
        raise ValueError("not a SyncBridge exchange file")
    major = str(envelope.get("schema_version", "")).split(".")[0]
    if major != SCHEMA_VERSION.split(".")[0]:
        raise ValueError("unsupported schema_version %r" % envelope.get("schema_version"))
    if kind is not None and envelope.get("kind") != kind:
        raise ValueError("expected kind %r, got %r" % (kind, envelope.get("kind")))
    return envelope["data"]


def load(path: str, kind: Optional[str] = None) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        env = json.load(f)
    check(env, kind)
    return env


def save(path: str, envelope: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2, ensure_ascii=False)
