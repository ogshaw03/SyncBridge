"""FastAPI application of the Local Sync Server.

    GET /health   {"app": "syncbridge", "version", "protocol", "clients"}   (no secrets)
    WS  /ws       first message must be `hello` with the session token
    /admin/*      admin API for the monitor, token required (admin.py, D-15)
"""
from __future__ import annotations

import asyncio
import contextlib
import hmac
import logging
import time
import types
from typing import Callable, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .. import __version__, protocol
from . import hubstate
from .admin import create_admin_router
from .connections import ConnectionManager
from .flow import TransferFlow
from .guide_flow import GuideFlow

log = logging.getLogger("syncbridge.server")

HELLO_TIMEOUT = 10.0
CLOSE_AUTH = 4401        # application close codes (4000-4999)
CLOSE_PROTOCOL = 4400
CLOSE_REPLACED = 4409
LOGGERS = ("syncbridge", "uvicorn.error")   # what the monitor sees (not uvicorn.access)
LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"


def create_app(token: str, idle_timeout: Optional[float] = None,
               on_idle: Optional[Callable[[], None]] = None,
               export_timeout: Optional[float] = None,
               apply_timeout: Optional[float] = None,
               on_shutdown: Optional[Callable[[], None]] = None,
               port: Optional[int] = None,
               log_file: Optional[str] = None) -> FastAPI:
    """Build the app. `on_idle` is called once no client has been connected for `idle_timeout` s;
    `on_shutdown` by POST /admin/shutdown. `log_file` also receives the log lines the monitor sees.

    The log handlers are attached in the lifespan: uvicorn reconfigures its loggers when it
    starts and would drop handlers attached earlier."""
    manager = ConnectionManager()
    bus = hubstate.EventBus()
    logbuf = hubstate.LogBuffer(bus)
    history = hubstate.TransferHistory(bus)
    flow_args = {}
    if export_timeout is not None:
        flow_args["export_timeout"] = export_timeout
    if apply_timeout is not None:
        flow_args["apply_timeout"] = apply_timeout
    flow = TransferFlow(manager, history=history, **flow_args)
    guides = GuideFlow(manager, history=history,
                       **({"timeout": export_timeout} if export_timeout is not None else {}))
    state = types.SimpleNamespace(manager=manager, flow=flow, history=history, logbuf=logbuf, bus=bus,
                                  started=time.monotonic(), started_iso=hubstate.now_iso(),
                                  port=port, log=log)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        bus.bind(asyncio.get_running_loop())
        handlers = [logbuf]
        if log_file:
            try:
                fh = logging.FileHandler(log_file, encoding="utf-8")
                fh.setFormatter(logging.Formatter(LOG_FORMAT))
                handlers.append(fh)
            except OSError as exc:
                log.warning("cannot write the log file %s: %s", log_file, exc)
        for name in LOGGERS:
            for h in handlers:
                logging.getLogger(name).addHandler(h)
        if log.getEffectiveLevel() > logging.INFO:
            log.setLevel(logging.INFO)          # the monitor shows connects and transfers
        task = None
        if idle_timeout and on_idle:
            task = asyncio.create_task(_idle_watch(manager, idle_timeout, on_idle))
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
            for name in LOGGERS:
                for h in handlers:
                    logging.getLogger(name).removeHandler(h)
            for h in handlers[1:]:
                h.close()

    app = FastAPI(title="SyncBridge Sync Server", version=__version__, lifespan=lifespan)
    app.state.manager = manager
    app.state.flow = flow
    app.state.hub = state
    app.include_router(create_admin_router(token, state, on_shutdown))

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
        bus.publish({"event": "client.connected", "client": client.summary()})
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
                if msg["kind"] in ("transfer.request", "guide.request"):
                    if msg["kind"] == "transfer.request":
                        log.info("%s requests %s", client.client_id, msg["data"].get("direction"))
                        task = asyncio.create_task(_transfer(flow, client, msg))
                    else:
                        log.info("%s sends the comp guide %s", client.client_id, msg["data"].get("comp"))
                        task = asyncio.create_task(_transfer(guides, client, msg))
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
            bus.publish({"event": "client.disconnected", "client": client.summary()})
            await manager.broadcast_peers()

    return app


async def _transfer(flow, client, msg) -> None:
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
