"""Manual transfer over the server (docs/PHASE1_PLAN.md 2).

    requester --transfer.request--> server
    server --export.request--> source app, target app
    server: syncbridge.core.jobs (same conversion as the CLI)
    server --apply.request--> target app (the user confirms there)
    server --transfer.result--> requester
"""
from __future__ import annotations

import asyncio

from .. import protocol
from ..core import envelope, jobs
from .connections import Client, ConnectionManager, RequestFailed

EXPORT_KIND = {"maya": "maya.timewarp.export", "ae": "ae.timeremap.export"}
EXPORT_TIMEOUT = 60.0
APPLY_TIMEOUT = 600.0   # the target app waits for the user's confirmation


class TransferFlow:
    def __init__(self, manager: ConnectionManager, export_timeout: float = EXPORT_TIMEOUT,
                 apply_timeout: float = APPLY_TIMEOUT, history=None):
        self.manager = manager
        self.export_timeout = export_timeout
        self.apply_timeout = apply_timeout
        self.history = history          # hubstate.TransferHistory (optional)
        self._lock = asyncio.Lock()

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    async def handle(self, requester: Client, request: dict) -> None:
        """Run one transfer.request and answer it (never raises)."""
        item = self.history.start(requester.client_id, request) if self.history else None
        if self._lock.locked():
            await self._fail(item, requester, request, protocol.E_BUSY, "another transfer is in progress")
            return
        async with self._lock:
            try:
                result = await self._run(requester, request)
            except RequestFailed as exc:
                await self._fail(item, requester, request, exc.code, exc.message)
                return
            except ValueError as exc:  # unusable input (no Scene Time Warp, no Time Remap, ...)
                await self._fail(item, requester, request, protocol.E_CONVERSION, str(exc))
                return
            except Exception as exc:  # report, never kill the connection loop
                await self._fail(item, requester, request, protocol.E_CONVERSION,
                                 "%s: %s" % (type(exc).__name__, exc))
                return
            if item is not None:
                self.history.finish(item, result=result)
            await self.manager.send(requester, protocol.reply(request, result))

    async def _fail(self, item, requester: Client, request: dict, code: str, message: str) -> None:
        if item is not None:
            self.history.finish(item, error_code=code, message=message)
        await self._answer_error(requester, request, code, message)

    async def _run(self, requester: Client, request: dict) -> dict:
        data = request["data"]
        direction = data["direction"]
        src_app, dst_app = protocol.DIRECTIONS[direction]
        try:
            opts = jobs.TransferOptions.from_json(data.get("options"))
        except (TypeError, ValueError) as exc:
            raise RequestFailed(protocol.E_BAD_MESSAGE, "options: %s" % exc)

        source = requester if requester.app == src_app else self.manager.pick(src_app, data.get("source"))
        target = self.manager.pick(dst_app, data.get("target"))
        src_export = await self._export(source, src_app)
        dst_export = await self._export(target, dst_app)

        if direction == "maya2ae":
            job = await asyncio.to_thread(jobs.maya_to_ae_job, src_export["data"], dst_export["data"], opts)
        else:
            job = await asyncio.to_thread(jobs.ae_to_maya_job, src_export["data"], dst_export["data"], opts)
        summary = {
            "direction": direction,
            "source": source.summary(),
            "target": target.summary(),
            "report": job.result.to_json(),
        }
        if not job.passed:
            # Do not touch the target when the conversion is outside tolerance (SPEC 5).
            summary.update(status=protocol.FAILED,
                           message="conversion is outside the tolerance; nothing was applied")
            return summary

        apply_env = job.apply_envelope("server")
        reply = await self.manager.request(target, "apply.request", {"apply": apply_env},
                                           self.apply_timeout)
        result = reply["data"]
        summary["status"] = result["status"]
        for key in ("backup", "message", "app_readback"):
            if key in result:
                summary[key] = result[key]
        if result["status"] == protocol.APPLIED and result.get("after"):
            report = jobs.readback(apply_env, result["after"], opts.tolerance_frames)
            summary["readback"] = report.to_json()
            if not report.passed:
                summary["message"] = "applied, but the target app evaluates it differently (readback failed)"
        return summary

    async def _export(self, client: Client, app: str) -> dict:
        reply = await self.manager.request(client, "export.request", {}, self.export_timeout)
        export = reply["data"]["export"]
        try:
            envelope.check(export, EXPORT_KIND[app])
        except ValueError as exc:
            raise RequestFailed(protocol.E_APP, "%s sent an invalid export: %s" % (client.client_id, exc))
        return export

    async def _answer_error(self, requester: Client, request: dict, code: str, message: str,
                            ) -> None:
        try:
            await self.manager.send(requester, protocol.error(code, message, reply_to=request["event_id"]))
        except Exception:
            pass
