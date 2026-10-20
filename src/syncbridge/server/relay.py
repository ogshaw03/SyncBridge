"""Requests from AE that the hub validates and relays to Maya (D-16, D-18).

    requester (AE) --<name>.request--> hub
    hub --<name>.apply.request--> Maya    (Maya does the work with syncbridge.core)
    hub --<name>.result--> requester

    guide    the comp frame shown in the Maya view (core.comp_guide; display only)
    markers  the Time Remap key timings as Maya markers (core.markers; saved in the scene)

Recorded in the transfer history with the data type of the flow.
"""
from __future__ import annotations

from .. import protocol
from ..core import comp_guide, envelope
from .connections import Client, ConnectionManager, RequestFailed

RELAY_TIMEOUT = 30.0
NO_MAYA = u"Maya が接続されていません。Maya の SyncBridge パネルで Connect を押してください。"


class RelayToMaya:
    """Base: validate a request from AE, ask Maya, answer the requester (never raises)."""
    DATA_TYPE = ""
    MAYA_KIND = ""

    def __init__(self, manager: ConnectionManager, timeout: float = RELAY_TIMEOUT, history=None):
        self.manager = manager
        self.timeout = timeout
        self.history = history

    def payload(self, data: dict) -> dict:
        """The data for Maya; raises RequestFailed for a bad request."""
        raise NotImplementedError

    def finish(self, result: dict) -> dict:
        return result

    async def handle(self, requester: Client, request: dict) -> None:
        item = None
        if self.history is not None:
            item = self.history.start(requester.client_id, {"data": {"direction": "ae2maya",
                                                                     "data_type": self.DATA_TYPE}})
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
        payload = self.payload(data)
        try:
            target = self.manager.pick("maya", data.get("target"))
        except RequestFailed as exc:
            raise RequestFailed(exc.code, NO_MAYA)
        reply = await self.manager.request(target, self.MAYA_KIND, payload, self.timeout)
        result = dict(reply["data"])
        result.update(source=requester.summary(), target=target.summary())
        return self.finish(result)

    async def _fail(self, item, requester: Client, request: dict, code: str, message: str) -> None:
        if item is not None:
            self.history.finish(item, error_code=code, message=message)
        try:
            await self.manager.send(requester, protocol.error(code, message, reply_to=request["event_id"]))
        except Exception:
            pass


class GuideFlow(RelayToMaya):
    """guide.request {comp: {name, width, height, pixelAspect}} (D-16)."""
    DATA_TYPE = "comp_guide"
    MAYA_KIND = "guide.apply.request"

    def payload(self, data: dict) -> dict:
        try:
            comp = comp_guide.parse_comp(data["comp"])
        except ValueError as exc:
            raise RequestFailed(protocol.E_BAD_MESSAGE, "comp: %s" % exc)
        return {"guide": {"name": comp["name"], "width": comp["width"], "height": comp["height"],
                          "pixelAspect": comp["pixel_aspect"]}}

    def finish(self, result: dict) -> dict:
        if result.get("warnings") and not result.get("message"):
            result["message"] = " / ".join(result["warnings"])
        return result


class MarkerFlow(RelayToMaya):
    """markers.request {export: ae.timeremap.export envelope, options: {origin, ...}} (D-18).

    Maya converts the key times with its own frame rate (core.markers), stores the markers in
    the scene and makes the time slider bookmarks and the viewport overlay.
    """
    DATA_TYPE = "key_markers"
    MAYA_KIND = "markers.apply.request"

    def payload(self, data: dict) -> dict:
        export = data["export"]
        try:
            envelope.check(export, "ae.timeremap.export")
        except ValueError as exc:
            raise RequestFailed(protocol.E_BAD_MESSAGE, "export: %s" % exc)
        if not export["data"].get("keys"):
            layer = (export["data"].get("layer") or {}).get("name", "")
            raise RequestFailed(protocol.E_CONVERSION,
                                u"レイヤー「%s」のタイムリマップにキーがありません。何も送っていません。" % layer)
        options = data.get("options") or {}
        if not isinstance(options, dict):
            raise RequestFailed(protocol.E_BAD_MESSAGE, "options must be an object")
        return {"export": export, "options": options}
