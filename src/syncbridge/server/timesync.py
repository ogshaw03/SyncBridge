"""Time slider sync relay (D-22).

One shared switch for all apps: a panel sends time.sync {enabled, follow_playback}; the hub
keeps it and tells every client (time.sync.state, also to an app that connects later).
While it is on, time.update {t} from one app goes to the other app as time.set {t, source};
t is AE comp time in seconds (Maya converts with its origin frame). No replies, no history:
these are frequent and only the latest one matters.
"""
from __future__ import annotations

import logging
from typing import Optional

from .. import protocol
from .connections import Client, ConnectionManager

log = logging.getLogger("syncbridge.server")

PEER_APP = {"maya": "ae", "ae": "maya"}


class TimeSync:
    def __init__(self, manager: ConnectionManager):
        self.manager = manager
        self.enabled = False
        self.follow_playback = False
        self.changed_by: Optional[str] = None

    def state(self) -> dict:
        return {"enabled": self.enabled, "follow_playback": self.follow_playback, "by": self.changed_by}

    async def send_state(self, client: Client) -> None:
        try:
            await self.manager.send(client, protocol.message("time.sync.state", self.state()))
        except Exception:
            pass

    async def handle(self, client: Client, msg: dict) -> None:
        if msg["kind"] == "time.sync":
            await self._switch(client, msg["data"])
        elif msg["kind"] == "time.update":
            await self._relay(client, msg["data"])

    async def _switch(self, client: Client, data: dict) -> None:
        self.enabled = bool(data["enabled"])
        if "follow_playback" in data:
            self.follow_playback = bool(data["follow_playback"])
        self.changed_by = client.client_id
        log.info("time slider sync %s by %s (follow playback: %s)", "on" if self.enabled else "off",
                 client.client_id, self.follow_playback)
        for other in list(self.manager.clients.values()):
            await self.send_state(other)

    async def _relay(self, client: Client, data: dict) -> None:
        peer_app = PEER_APP.get(client.app)
        if not self.enabled or peer_app is None:
            return
        out = {"t": float(data["t"]), "source": client.app}
        if isinstance(data.get("sent_at"), (int, float)):
            out["sent_at"] = data["sent_at"]          # the receiver measures the delay (D-22)
        msg = protocol.message("time.set", out)
        for other in list(self.manager.clients.values()):
            if other.app == peer_app:
                try:
                    await self.manager.send(other, msg)
                except Exception:          # a closing socket must not stop the others
                    pass
