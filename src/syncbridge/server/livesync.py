"""Live sync of AE layers to Maya (D-41).

One shared switch, like the time slider sync (D-22): a panel sends live.sync {enabled}; the hub keeps it
with the AE layers to watch (live.watch {layers} from Maya: the linked ones) and tells every client
(live.sync.state {enabled, layers, by}, also to an app that connects later). While it is on, the AE panel
watches those layers and sends live.changed {layers} when the user is done changing one; the hub hands it
to Maya, which reads the layer's motion again (motion.request) and updates the dedicated camera.
No replies, no history.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from .. import protocol
from .connections import Client, ConnectionManager

log = logging.getLogger("syncbridge.server")


class LiveSync:
    def __init__(self, manager: ConnectionManager):
        self.manager = manager
        self.enabled = False
        self.layers: List[dict] = []
        self.changed_by: Optional[str] = None

    def state(self) -> dict:
        return {"enabled": self.enabled, "layers": list(self.layers), "by": self.changed_by}

    async def send_state(self, client: Client) -> None:
        try:
            await self.manager.send(client, protocol.message("live.sync.state", self.state()))
        except Exception:
            pass

    async def _broadcast(self) -> None:
        for other in list(self.manager.clients.values()):
            await self.send_state(other)

    async def handle(self, client: Client, msg: dict) -> None:
        data = msg["data"]
        if msg["kind"] == "live.sync":
            self.enabled = bool(data["enabled"])
            self.changed_by = client.client_id
            log.info("live sync %s by %s", "on" if self.enabled else "off", client.client_id)
            await self._broadcast()
        elif msg["kind"] == "live.watch":
            self.layers = [dict(x) for x in data["layers"]]
            await self._broadcast()
        elif msg["kind"] == "live.changed":
            if not self.enabled:
                return
            out = protocol.message("live.changed", {"layers": list(data["layers"]), "source": client.app})
            for other in list(self.manager.clients.values()):
                if other.app == "maya":
                    try:
                        await self.manager.send(other, out)
                    except Exception:          # a closing socket must not stop the others
                        pass
