"""FastAPI application of the Local Sync Server.

    GET /health   {"app": "syncbridge", "version", "protocol", "clients"}   (no secrets)
    WS  /ws       first message must be `hello` with the session token
"""
from __future__ import annotations

import asyncio
import contextlib
import hmac
import logging
import time
from typing import Callable, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .. import __version__, protocol
from .connections import ConnectionManager
from .flow import TransferFlow

log = logging.getLogger("syncbridge.server")

HELLO_TIMEOUT = 10.0
CLOSE_AUTH = 4401        # application close codes (4000-4999)
CLOSE_PROTOCOL = 4400
CLOSE_REPLACED = 4409


def create_app(token: str, idle_timeout: Optional[float] = None,
               on_idle: Optional[Callable[[], None]] = None,
               export_timeout: Optional[float] = None,
               apply_timeout: Optional[float] = None) -> FastAPI:
    """Build the app. `on_idle` is called once no client has been connected for `idle_timeout` s."""
    manager = ConnectionManager()
    flow_args = {}
    if export_timeout is not None:
        flow_args["export_timeout"] = export_timeout
    if apply_timeout is not None:
        flow_args["apply_timeout"] = apply_timeout
    flow = TransferFlow(manager, **flow_args)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        task = None
        if idle_timeout and on_idle:
            task = asyncio.create_task(_idle_watch(manager, idle_timeout, on_idle))
        yield
        if task is not None:
            task.cancel()

    app = FastAPI(title="SyncBridge Sync Server", version=__version__, lifespan=lifespan)
    app.state.manager = manager
    app.state.flow = flow

    @app.get("/health")
    async def health():
        return {"app": "syncbridge", "version": __version__,
                "protocol": protocol.PROTOCOL_VERSION, "clients": len(manager.clients)}

    @app.websocket(protocol.WS_PATH)
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        try:
            hello = protocol.decode(await asyncio.wait_for(ws.receive_text(), HELLO_TIMEOUT))
        except (asyncio.TimeoutError, protocol.ProtocolError, WebSocketDisconnect) as exc:
            await _reject(ws, protocol.E_BAD_MESSAGE, "expected hello: %s" % exc, CLOSE_PROTOCOL)
            return
        if hello["kind"] != "hello":
            await _reject(ws, protocol.E_BAD_MESSAGE, "first message must be hello", CLOSE_PROTOCOL)
            return
        if not hmac.compare_digest(str(hello["data"]["token"]), token):
            log.warning("rejected a client with a wrong token")
            await _reject(ws, protocol.E_AUTH, "invalid session token", CLOSE_AUTH)
            return

        client = manager.add(hello, ws.send_text, ws.close)
        log.info("connected %s (%s)", client.client_id, client.document or "-")
        for old in manager.superseded_by(client):
            log.info("closing %s: replaced by %s from the same process", old.client_id, client.client_id)
            await _replace(old, client)
        tasks = set()
        try:
            await manager.send(client, protocol.message("welcome", {
                "client_id": client.client_id, "server_version": __version__,
                "protocol": protocol.PROTOCOL_VERSION}, reply_to=hello["event_id"]))
            await manager.broadcast_peers()
            while True:
                text = await ws.receive_text()
                try:
                    msg = protocol.decode(text)
                except protocol.ProtocolError as exc:
                    await manager.send(client, protocol.error(exc.code, exc.message))
                    continue
                if msg.get("reply_to") and manager.resolve(client, msg):
                    continue
                if msg["kind"] == "transfer.request":
                    log.info("%s requests %s", client.client_id, msg["data"]["direction"])
                    task = asyncio.create_task(_transfer(flow, client, msg))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
                    continue
                await manager.send(client, protocol.error(
                    protocol.E_BAD_MESSAGE, "unexpected %s" % msg["kind"], reply_to=msg["event_id"]))
        except WebSocketDisconnect:
            pass
        finally:
            manager.remove(client)
            log.info("disconnected %s", client.client_id)
            await manager.broadcast_peers()

    return app


async def _transfer(flow: TransferFlow, client, msg) -> None:
    await flow.handle(client, msg)
    log.info("transfer by %s finished", client.client_id)


async def _replace(old, new) -> None:
    """Tell a stale connection it was replaced, then close it (its loop then removes it)."""
    try:
        await old.send_text(protocol.encode(protocol.error(
            protocol.E_REPLACED, "replaced by a newer connection (%s) from the same process" % new.client_id)))
        if old.close is not None:
            await old.close(code=CLOSE_REPLACED)
    except Exception:
        pass


async def _reject(ws: WebSocket, code: str, message: str, close_code: int) -> None:
    try:
        await ws.send_text(protocol.encode(protocol.error(code, message)))
        await ws.close(code=close_code)
    except Exception:
        pass


async def _idle_watch(manager: ConnectionManager, idle_timeout: float, on_idle) -> None:
    """Call on_idle once nobody has been connected for idle_timeout seconds (SPEC 8: stop after both apps exit)."""
    while True:
        await asyncio.sleep(min(5.0, idle_timeout / 4.0))
        since = manager.idle_since
        if since is not None and time.monotonic() - since >= idle_timeout:
            log.info("no clients for %g s; shutting down", idle_timeout)
            on_idle()
            return


__all__ = ["create_app"]
