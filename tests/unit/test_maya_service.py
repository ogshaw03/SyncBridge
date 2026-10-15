"""Maya service glue (Phase 1-B) with a fake maya package; the Qt UI is syntax-checked only."""
import ast
import os
import sys
import types
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAYA_SCRIPTS = os.path.join(REPO, "maya_plugin", "scripts")


def _maya_modules():
    return [k for k in sys.modules if k == "maya" or k.startswith(("maya.", "syncbridge_maya"))]


class MayaServiceTest(unittest.TestCase):
    def setUp(self):
        self.saved = {k: sys.modules.pop(k) for k in _maya_modules()}
        maya = types.ModuleType("maya")
        cmds = types.ModuleType("maya.cmds")
        cmds.warnings = []
        cmds.warning = cmds.warnings.append
        cmds.about = lambda **kw: "2024"
        cmds.file = lambda **kw: "shot.mb"
        utils = types.ModuleType("maya.utils")
        utils.executeDeferred = lambda fn: fn()
        maya.cmds, maya.utils, maya.mel = cmds, utils, types.ModuleType("maya.mel")
        sys.modules.update({"maya": maya, "maya.cmds": cmds, "maya.utils": utils, "maya.mel": maya.mel})
        sys.path.insert(0, MAYA_SCRIPTS)
        from syncbridge_maya import exchange, service
        self.exchange, self.service, self.cmds = exchange, service, cmds
        self.calls = []

    def tearDown(self):
        sys.path.remove(MAYA_SCRIPTS)
        for k in _maya_modules():
            del sys.modules[k]
        sys.modules.update(self.saved)

    def test_export_handler_allows_missing_curve(self):
        self.exchange.build_export = lambda **kw: self.calls.append(kw) or {"kind": "maya.timewarp.export"}
        reply = self.service._handle_export({"data": {}})
        self.assertEqual(reply, {"export": {"kind": "maya.timewarp.export"}})
        self.assertEqual(self.calls, [{"allow_missing": True}])

    def test_apply_handler_confirms_and_reports(self):
        apply_env = {"kind": "maya.timewarp.apply", "data": {"native": {"keys": [{}, {}]}}}

        def fake_apply(env, confirm, origin):
            self.calls.append((env, confirm, origin))
            return {"status": "applied", "app_readback": {"passed": True, "max_error_frames": 0.0}}
        self.exchange.apply_envelope = fake_apply
        events = []
        self.service.add_listener(lambda e, p: events.append((e, p)))
        reply = self.service._handle_apply({"data": {"apply": apply_env}})
        self.assertEqual(reply["status"], "applied")
        self.assertEqual(self.calls, [(apply_env, True, "After Effects")])
        self.assertEqual(events[0][0], "applied")
        self.assertEqual(events[0][1]["keys"], 2)
        self.assertTrue(events[0][1]["readback"]["passed"])

    def test_apply_handler_reports_failure(self):
        def fake_apply(env, confirm, origin):
            raise RuntimeError("This scene has no Scene Time Warp")
        self.exchange.apply_envelope = fake_apply
        events = []
        self.service.add_listener(lambda e, p: events.append((e, p)))
        with self.assertRaises(RuntimeError):
            self.service._handle_apply({"data": {"apply": {"data": {"native": {"keys": []}}}}})
        self.assertEqual(events, [("applied", {"status": "failed", "message": "This scene has no Scene Time Warp"})])

    def test_transfer_requires_connection(self):
        from syncbridge.client.sync_client import ConnectError
        with self.assertRaises(ConnectError):
            self.service.send_to_ae({"origin": 1})

    def test_transfer_results_reach_listeners(self):
        sent = {}

        class FakeClient:
            connected = True
            client_id = "maya-1"
            peers = []

            def request_transfer(self, direction, options, callback):
                sent.update(direction=direction, options=options, callback=callback)
                return "event-1"

        self.service._client = FakeClient()
        events = []
        self.service.add_listener(lambda e, p: events.append((e, p)))
        self.service.send_to_ae({"origin": 1})
        self.assertEqual(sent["direction"], "maya2ae")
        result = {"kind": "transfer.result", "data": {
            "direction": "maya2ae", "status": "applied",
            "report": {"conversion": {"max_error_frames": 0.0}, "warnings": ["w1"]}}}
        sent["callback"](result)
        self.assertEqual(events, [("transfer_result", result)])
        self.assertEqual(self.cmds.warnings, ["SyncBridge: w1"])
        sent["callback"]({"kind": "error", "data": {"message": "no ae client is connected"}})
        self.assertIn("no ae client", self.cmds.warnings[-1])

    def test_ui_module_parses(self):
        with open(os.path.join(MAYA_SCRIPTS, "syncbridge_maya", "ui.py"), encoding="utf-8") as f:
            ast.parse(f.read())


if __name__ == "__main__":
    unittest.main()
