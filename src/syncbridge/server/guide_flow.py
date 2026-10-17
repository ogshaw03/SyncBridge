"""Comp guide over the hub (D-16): AE's comp frame shown in the Maya view.

    requester (AE) --guide.request {comp}--> hub
    hub --guide.apply.request {guide}--> Maya    (draws it; no confirmation, not scene data)
    hub --guide.result--> requester

The hub only validates and relays; Maya computes the frame from its own camera and render
resolution (syncbridge.core.comp_guide). Recorded in the transfer history as data type
"comp_guide".
"""
from __future__ import annotations

from .. import protocol
from ..core import comp_guide
from .connections import Client, ConnectionManager, RequestFailed

GUIDE_TIMEOUT = 30.0
DATA_TYPE = "comp_guide"


class GuideFlow:
    def __init__(self, manager: ConnectionManager, timeout: float = GUIDE_TIMEOUT, history=None):
        self.manager = manager
        self.timeout = timeout
        self.history = history

    async def handle(self, requester: Client, request: dict) -> None:
        """Answer one guide.request (never raises)."""
        item = None
        if self.history is not None:
            item = self.history.start(requester.client_id, {"data": {"direction": "ae2maya",
                                                                     "data_type": DATA_TYPE}})
        try:
            result = await self._run(requester, request)
        except RequestFailed as exc:
            await self._fail(item, requester, request, exc.code, exc.message)
            return
        except Exception as exc:  # report, never kill the connection loop
            await self._fail(item, requester, request, protocol.E_APP, "%s: %s" % (type(exc).__name__, exc))
            return
        if item is not None:
            self.history.finish(item, result=result)
        await self.manager.send(requester, protocol.reply(request, result))

    async def _run(self, requester: Client, request: dict) -> dict:
        data = request["data"]
        try:
            comp = comp_guide.parse_comp(data["comp"])
        except ValueError as exc:
            raise RequestFailed(protocol.E_BAD_MESSAGE, "comp: %s" % exc)
        try:
            target = self.manager.pick("maya", data.get("target"))
        except RequestFailed as exc:
            raise RequestFailed(exc.code, u"Maya が接続されていません。Maya の SyncBridge パネルで Connect を押してください。")
        guide = {"name": comp["name"], "width": comp["width"], "height": comp["height"],
                 "pixelAspect": comp["pixel_aspect"]}
        reply = await self.manager.request(target, "guide.apply.request", {"guide": guide}, self.timeout)
        result = dict(reply["data"])
        result.update(source=requester.summary(), target=target.summary())
        if result.get("warnings") and not result.get("message"):
            result["message"] = " / ".join(result["warnings"])
        return result

    async def _fail(self, item, requester: Client, request: dict, code: str, message: str) -> None:
        if item is not None:
            self.history.finish(item, error_code=code, message=message)
        try:
            await self.manager.send(requester, protocol.error(code, message, reply_to=request["event_id"]))
        except Exception:
            pass
