"""Scene settings transfer over the hub (D-21).

    requester --settings.request {direction, items, options: {origin}}--> hub
    hub --settings.export.request--> source app, target app      (current settings)
    hub: syncbridge.core.scene_sync makes the plan (the values to change)
    hub --settings.apply.request {plan, message}--> target app   (the user confirms there)
    hub --settings.result--> requester

Nothing is sent to the target when there is nothing to change ("unchanged").
Recorded in the transfer history with the data type "scene_settings".
"""
from __future__ import annotations

import asyncio

from .. import protocol
from ..core import scene_sync
from .connections import Client, ConnectionManager, RequestFailed

EXPORT_TIMEOUT = 60.0
APPLY_TIMEOUT = 600.0   # the target app waits for the user's confirmation
APP_NAMES = {"maya": u"Maya のシーン", "ae": u"After Effects のコンプ"}


class SettingsFlow:
    DATA_TYPE = "scene_settings"

    def __init__(self, manager: ConnectionManager, export_timeout: float = EXPORT_TIMEOUT,
                 apply_timeout: float = APPLY_TIMEOUT, history=None):
        self.manager = manager
        self.export_timeout = export_timeout
        self.apply_timeout = apply_timeout
        self.history = history
        self._lock = asyncio.Lock()

    async def handle(self, requester: Client, request: dict) -> None:
        """Run one settings.request and answer it (never raises)."""
        data = request["data"]
        item = None
        if self.history is not None:
            item = self.history.start(requester.client_id, {"data": {"direction": data.get("direction"),
                                                                     "data_type": self.DATA_TYPE}})
        if self._lock.locked():
            await self._fail(item, requester, request, protocol.E_BUSY, u"ほかの設定の転送が実行中です。")
            return
        async with self._lock:
            try:
                result = await self._run(requester, data)
            except RequestFailed as exc:
                await self._fail(item, requester, request, exc.code, exc.message)
                return
            except ValueError as exc:            # a setting the target cannot take (Japanese message)
                await self._fail(item, requester, request, protocol.E_CONVERSION, str(exc))
                return
            except Exception as exc:  # report, never kill the connection loop
                await self._fail(item, requester, request, protocol.E_APP, "%s: %s" % (type(exc).__name__, exc))
                return
        if item is not None:
            self.history.finish(item, result=result)
        await self.manager.send(requester, protocol.reply(request, result))

    async def _run(self, requester: Client, data: dict) -> dict:
        direction = data["direction"]
        src_app, dst_app = protocol.DIRECTIONS[direction]
        options = data.get("options") or {}
        if not isinstance(options, dict):
            raise RequestFailed(protocol.E_BAD_MESSAGE, "options must be an object")
        try:
            origin = float(options.get("origin", 1.0))
        except (TypeError, ValueError):
            raise RequestFailed(protocol.E_BAD_MESSAGE, "options.origin must be a number")
        source = requester if requester.app == src_app else self._pick(src_app)
        target = self._pick(dst_app)
        src = await self._export(source)
        dst = await self._export(target)
        plan = scene_sync.make_plan(direction, src, dst, data.get("items"), origin)
        summary = {"direction": direction, "source": source.summary(), "target": target.summary(),
                   "changes": plan["changes"], "warnings": plan["warnings"]}
        if not plan["apply"]:
            summary.update(status=protocol.UNCHANGED, message=u"%s はすでに同じ設定です。" % APP_NAMES[dst_app])
            return summary
        label = APP_NAMES[src_app]
        if src_app == "ae" and src.get("comp"):
            label = u"After Effects のコンプ「%s」" % src["comp"]
        message = scene_sync.confirm_text(plan, label)
        reply = await self.manager.request(target, "settings.apply.request", {"plan": plan, "message": message},
                                           self.apply_timeout)
        result = reply["data"]
        summary["status"] = result["status"]
        for key in ("backup", "message"):
            if key in result:
                summary[key] = result[key]
        if result["status"] == protocol.APPLIED and result.get("after"):
            problems = scene_sync.check_after(plan, result["after"])
            summary["readback"] = {"passed": not problems, "problems": problems}
            if problems:
                summary["message"] = u"適用しましたが、%s の値が送った値と違います: %s" % (
                    APP_NAMES[dst_app], ", ".join(p["key"] for p in problems))
        return summary

    def _pick(self, app: str) -> Client:
        try:
            return self.manager.pick(app)
        except RequestFailed as exc:
            name = "Maya" if app == "maya" else "After Effects"
            raise RequestFailed(exc.code, u"%s が接続されていません。%s の SyncBridge パネルで Connect を押してください。"
                                % (name, name))

    async def _export(self, client: Client) -> dict:
        reply = await self.manager.request(client, "settings.export.request", {}, self.export_timeout)
        settings = reply["data"]["settings"]
        if not isinstance(settings, dict):
            raise RequestFailed(protocol.E_APP, "%s sent invalid settings" % client.client_id)
        return settings

    async def _fail(self, item, requester: Client, request: dict, code: str, message: str) -> None:
        if item is not None:
            self.history.finish(item, error_code=code, message=message)
        try:
            await self.manager.send(requester, protocol.error(code, message, reply_to=request["event_id"]))
        except Exception:
            pass
