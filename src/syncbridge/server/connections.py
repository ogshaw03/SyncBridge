"""Connected clients and request/reply over WebSocket (asyncio)."""
from __future__ import annotations

import asyncio
import datetime
import itertools
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, List, Optional

from .. import protocol

Send = Callable[[str], Awaitable[None]]


class RequestFailed(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Client:
    client_id: str
    app: str
    send_text: Send
    version: str = ""
    pid: Optional[int] = None
    document: str = ""
    connected_at: str = ""
    seq: int = 0
    pending: Dict[str, asyncio.Future] = field(default_factory=dict)

    def summary(self) -> dict:
        return {"client_id": self.client_id, "app": self.app, "version": self.version,
                "pid": self.pid, "document": self.document, "connected_at": self.connected_at}


class ConnectionManager:
    def __init__(self):
        self.clients: Dict[str, Client] = {}
        self._ids = itertools.count(1)
        self.idle_since: Optional[float] = time.monotonic()

    # -- registry -------------------------------------------------------------
    def add(self, hello: dict, send_text: Send) -> Client:
        data = hello["data"]
        n = next(self._ids)
        client = Client(
            client_id="%s-%d" % (data["app"], n),
            app=data["app"],
            send_text=send_text,
            version=str(data.get("version", "")),
            pid=data.get("pid"),
            document=str(data.get("document", "")),
            connected_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            seq=n,
        )
        self.clients[client.client_id] = client
        self.idle_since = None
        return client

    def remove(self, client: Client) -> None:
        self.clients.pop(client.client_id, None)
        for fut in list(client.pending.values()):
            if not fut.done():
                fut.set_exception(RequestFailed(protocol.E_DISCONNECTED,
                                                "%s disconnected" % client.client_id))
        client.pending.clear()
        if not self.clients:
            self.idle_since = time.monotonic()

    def peers(self) -> List[dict]:
        return [c.summary() for c in sorted(self.clients.values(), key=lambda c: c.seq)]

    def pick(self, app: str, client_id: Optional[str] = None) -> Client:
        """A client of `app`: the given id, else the most recently connected one."""
        if client_id:
            client = self.clients.get(client_id)
            if client is None or client.app != app:
                raise RequestFailed(protocol.E_NO_PEER, "no %s client with id %r" % (app, client_id))
            return client
        candidates = [c for c in self.clients.values() if c.app == app]
        if not candidates:
            raise RequestFailed(protocol.E_NO_PEER, "no %s client is connected" % app)
        return max(candidates, key=lambda c: c.seq)

    # -- messaging --------------------------------------------------------------
    async def send(self, client: Client, msg: dict) -> None:
        await client.send_text(protocol.encode(msg))

    async def broadcast_peers(self) -> None:
        msg = protocol.message("peers", {"clients": self.peers()})
        for client in list(self.clients.values()):
            try:
                await self.send(client, msg)
            except Exception:  # a closing socket must not stop the broadcast
                pass

    async def request(self, client: Client, kind: str, data: dict, timeout: float) -> dict:
        """Send a request to `client` and wait for the message that replies to it."""
        msg = protocol.message(kind, data)
        fut = asyncio.get_running_loop().create_future()
        client.pending[msg["event_id"]] = fut
        try:
            await self.send(client, msg)
            reply = await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            raise RequestFailed(protocol.E_TIMEOUT, "%s did not answer %s within %g s"
                                % (client.client_id, kind, timeout))
        finally:
            client.pending.pop(msg["event_id"], None)
        if reply["kind"] == "error":
            raise RequestFailed(reply["data"].get("code", protocol.E_APP),
                                "%s: %s" % (client.client_id, reply["data"].get("message", "")))
        return reply

    def resolve(self, client: Client, msg: dict) -> bool:
        """Deliver a reply to the request waiting for it. False if nothing waits."""
        fut = client.pending.get(msg.get("reply_to"))
        if fut is None or fut.done():
            return False
        fut.set_result(msg)
        return True
