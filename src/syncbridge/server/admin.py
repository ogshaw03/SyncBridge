"""Admin API of the hub for the monitor and the launcher (D-15, docs/PLATFORM_DESIGN.md 5.3).

Loopback only like the rest of the hub, and every call needs the session token:
    HTTP: header  Authorization: Bearer <token>
    WS  : first message {"token": "<token>"} (no token in the URL: it would end up in access logs)

    GET  /admin/status                        version, pid, uptime, clients, transfer running
    GET  /admin/transfers?limit=50            recent transfers (newest last)
    GET  /admin/log?tail=200                  recent log lines (newest last)
    WS   /admin/events                        live: client.connected / client.disconnected /
                                              transfer.started / transfer.finished / log
    POST /admin/shutdown                      stop the hub normally
    POST /admin/clients/{client_id}/disconnect
"""
from __future__ import annotations

import asyncio
import hmac
import json
import os
import time
from typing import Callable, Optional

from fastapi import APIRouter, Header, HTTPException, WebSocket, WebSocketDisconnect

from .. import __version__, protocol

AUTH_TIMEOUT = 10.0
CLOSE_AUTH = 4401
CLOSE_BY_ADMIN = 4410
E_DISCONNECTED_BY_ADMIN = "disconnected_by_admin"


def create_admin_router(token: str, state, on_shutdown: Optional[Callable[[], None]] = None) -> APIRouter:
    """`state` has manager, flow, history, logbuf, bus, started (monotonic), started_iso, port."""
    router = APIRouter(prefix="/admin")

    def check(authorization: Optional[str]) -> None:
        expected = "Bearer " + token
        if not authorization or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="invalid or missing token")

    def status() -> dict:
        return {
            "app": "syncbridge",
            "version": __version__,
            "protocol": protocol.PROTOCOL_VERSION,
            "pid": os.getpid(),
            "port": state.port,
            "started": state.started_iso,
            "uptime_s": round(time.monotonic() - state.started, 1),
            "clients": state.manager.peers(),
            "transfer_running": state.flow.busy,
            "transfers_recorded": len(state.history.items),
        }

    @router.get("/status")
    async def get_status(authorization: Optional[str] = Header(None)):
        check(authorization)
        return status()

    @router.get("/transfers")
    async def get_transfers(limit: int = 50, authorization: Optional[str] = Header(None)):
        check(authorization)
        return {"transfers": state.history.recent(max(0, min(limit, 1000)))}

    @router.get("/log")
    async def get_log(tail: int = 200, authorization: Optional[str] = Header(None)):
        check(authorization)
        return {"lines": state.logbuf.tail(max(0, min(tail, 10000)))}

    @router.post("/shutdown")
    async def shutdown(authorization: Optional[str] = Header(None)):
        check(authorization)
        if on_shutdown is None:
            raise HTTPException(status_code=501, detail="this hub cannot be stopped through the API")
        state.log.info("shutdown requested through the admin API")
        # Answer first, then stop.
        asyncio.get_running_loop().call_later(0.2, on_shutdown)
        return {"status": "stopping"}

    @router.post("/clients/{client_id}/disconnect")
    async def disconnect(client_id: str, authorization: Optional[str] = Header(None)):
        check(authorization)
        client = state.manager.clients.get(client_id)
        if client is None:
            raise HTTPException(status_code=404, detail="no client %s" % client_id)
        state.log.info("disconnecting %s (admin request)", client_id)
        try:
            await client.send_text(protocol.encode(protocol.error(
                E_DISCONNECTED_BY_ADMIN, "disconnected from the SyncBridge monitor")))
            if client.close is not None:
                await client.close(code=CLOSE_BY_ADMIN)
        except Exception:
            pass
        return {"status": "disconnected", "client_id": client_id}

    @router.websocket("/events")
    async def events(ws: WebSocket):
        await ws.accept()
        try:
            first = json.loads(await asyncio.wait_for(ws.receive_text(), AUTH_TIMEOUT))
            ok = isinstance(first, dict) and hmac.compare_digest(str(first.get("token", "")), token)
        except (asyncio.TimeoutError, ValueError, WebSocketDisconnect):
            ok = False
        if not ok:
            try:
                await ws.send_text(json.dumps({"event": "error", "message": "invalid token"}))
                await ws.close(code=CLOSE_AUTH)
            except Exception:
                pass
            return
        queue = state.bus.subscribe()
        receiver = getter = None
        try:
            await ws.send_text(json.dumps({"event": "status", "status": status()}))
            receiver = asyncio.ensure_future(ws.receive_text())   # notices the monitor closing
            while True:
                getter = asyncio.ensure_future(queue.get())
                done, _ = await asyncio.wait({getter, receiver}, return_when=asyncio.FIRST_COMPLETED)
                if receiver in done:
                    break
                await ws.send_text(json.dumps(getter.result(), ensure_ascii=False))
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            state.bus.unsubscribe(queue)
            for task in (getter, receiver):
                if task is not None:
                    task.cancel()
                    task.add_done_callback(_consume)   # the hub may stop while a monitor listens

    return router


def _consume(task: "asyncio.Future") -> None:
    if not task.cancelled():
        task.exception()
