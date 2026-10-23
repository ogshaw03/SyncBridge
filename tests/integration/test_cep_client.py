"""AE panel client (sbclient.js) in Node against the real server, with a SyncClient as Maya.

Needs node (with the built-in WebSocket, Node 22+) and the server packages.
"""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest

from syncbridge.client.sync_client import SyncClient
from syncbridge.core import envelope

from .test_server import HAVE_SERVER, TOKEN, ServerFixture, _maya_after, ae_export, maya_export

DRIVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cep_driver.js")
MAYA_SETTINGS = {"fps": [24, 1], "time_unit": "film", "playback_range": [11, 34], "animation_range": [1, 120],
                 "pixel_aspect": 1.0, "resolution": [1920, 1080], "current_frame": 1.0}


def _node_ok():
    node = shutil.which("node")
    if not node:
        return False
    out = subprocess.run([node, "-e", "process.stdout.write(typeof WebSocket)"],
                         capture_output=True, encoding="utf-8", timeout=30)
    return out.stdout == "function"


@unittest.skipUnless(HAVE_SERVER and _node_ok(), "needs the server packages and Node 22+ (WebSocket)")
class CepClientTest(ServerFixture):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self.export_path = os.path.join(self.tmp, "ae_export.json")
        envelope.save(self.export_path, ae_export())
        self.applied = []
        self.maya = SyncClient("maya", {
            "export.request": lambda msg: {"export": maya_export()},
            "apply.request": self._maya_apply,
            "guide.apply.request": self._maya_guide,
            "markers.apply.request": self._maya_markers,
            "settings.export.request": lambda msg: {"settings": dict(MAYA_SETTINGS)},
            "settings.apply.request": self._maya_settings,
        }, notices={"time.set": lambda msg: self.times.append(msg["data"]["t"]),
                    "time.sync.state": lambda msg: self.states.append(msg["data"])})
        self.settings_plans = []
        self.times = []
        self.states = []
        self.markers = []
        self.guides = []
        self.maya.connect(port=self.port, token=TOKEN)
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            if p.poll() is None:
                p.kill()
            p.wait(10)
            for stream in (p.stdin, p.stdout):
                if stream:
                    stream.close()
        self.maya.disconnect()
        shutil.rmtree(self.tmp)
        super().tearDown()

    def _maya_apply(self, msg):
        env = msg["data"]["apply"]
        self.applied.append(env)
        return {"status": "applied", "after": _maya_after(env["data"]["native"])}

    def _maya_guide(self, msg):
        guide = msg["data"]["guide"]
        self.guides.append(guide)
        return {"status": "applied", "camera": "persp", "render": [2112, 1188],
                "comp": [guide["width"], guide["height"]], "warnings": []}

    def _maya_markers(self, msg):
        self.markers.append(msg["data"])
        return {"status": "applied", "count": len(msg["data"]["export"]["data"]["keys"]),
                "first": "1001", "last": "1097", "bookmarks": 4}

    def _maya_settings(self, msg):
        plan = msg["data"]["plan"]
        self.settings_plans.append(msg["data"])
        return {"status": "applied", "after": dict(MAYA_SETTINGS, **{k: v for k, v in plan["apply"].items()
                                                                     if k in MAYA_SETTINGS},
                                                  fps=[24, 1])}

    def driver(self, *args, export=None):
        p = subprocess.Popen(["node", DRIVER, str(self.port), TOKEN, export or self.export_path] + list(args),
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             encoding="utf-8")
        self.procs.append(p)
        events = []
        threading.Thread(target=lambda: [events.append(json.loads(line)) for line in p.stdout
                                         if line.startswith("{")], daemon=True).start()
        return p, events

    def wait(self, predicate, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return True
            time.sleep(0.05)
        return False

    def test_panel_receives_maya_to_ae(self):
        p, events = self.driver("serve")
        self.assertTrue(self.wait(lambda: any(e["event"] == "peers" and "ae" in e["peers"] for e in events)))
        self.assertTrue(self.wait(lambda: any(x["app"] == "ae" for x in self.maya.peers)))
        results = []
        self.maya.request_transfer("maya2ae", {"origin": 1}, results.append)
        self.assertTrue(self.wait(lambda: results))
        self.assertEqual(results[0]["kind"], "transfer.result", results[0])
        self.assertEqual(results[0]["data"]["status"], "applied")
        apply_events = [e for e in events if e["event"] == "apply"]
        self.assertEqual(len(apply_events), 1)
        self.assertEqual(apply_events[0]["kind"], "ae.timeremap.apply")
        self.assertEqual(apply_events[0]["origin"], "Maya")
        self.assertNotIn("readback", results[0]["data"])   # the fake host sends no `after`

    def test_panel_requests_ae_to_maya(self):
        p, events = self.driver("request", "ae2maya")
        self.assertEqual(p.wait(30), 0, events)
        result = [e for e in events if e["event"] == "result"][0]["reply"]
        self.assertEqual(result["kind"], "transfer.result", result)
        self.assertEqual(result["data"]["status"], "applied")
        self.assertTrue(result["data"]["readback"]["passed"])
        self.assertEqual(len(self.applied), 1)

    def test_panel_sends_the_comp_guide(self):
        # D-16: "解像度の枠を Maya へ" -> guide.request -> Maya draws the frame.
        p, events = self.driver("guide")
        self.assertEqual(p.wait(30), 0, events)
        reply = [e for e in events if e["event"] == "result"][0]["reply"]
        self.assertEqual(reply["kind"], "guide.result", reply)
        self.assertEqual((reply["data"]["status"], reply["data"]["camera"]), ("applied", "persp"))
        self.assertEqual(reply["data"]["target"]["client_id"], self.maya.client_id)
        self.assertEqual(self.guides, [{"name": "Comp 1", "width": 1920, "height": 1080, "pixelAspect": 1.0}])

    def test_comp_guide_without_a_comp(self):
        p, events = self.driver("guide", export="ERROR")
        self.assertEqual(p.wait(30), 0, events)
        reply = [e for e in events if e["event"] == "result"][0]["reply"]
        self.assertEqual(reply["kind"], "error")
        self.assertIn("コンポジションを開いてください", reply["data"]["message"])
        self.assertEqual(self.guides, [])

    def test_panel_sends_key_markers(self):
        # D-18: "キーのマーカーを Maya へ" -> the selected layer's export + the origin frame.
        p, events = self.driver("markers")
        self.assertEqual(p.wait(30), 0, events)
        reply = [e for e in events if e["event"] == "result"][0]["reply"]
        self.assertEqual(reply["kind"], "markers.result", reply)
        self.assertEqual(reply["data"]["count"], 4)
        self.assertEqual(self.markers[0]["options"], {"origin": 1001})
        self.assertEqual(self.markers[0]["export"]["kind"], "ae.timeremap.export")

    def test_key_markers_without_a_layer(self):
        p, events = self.driver("markers", export="ERROR")
        self.assertEqual(p.wait(30), 0, events)
        reply = [e for e in events if e["event"] == "result"][0]["reply"]
        self.assertEqual(reply["kind"], "error")
        self.assertIn(u"レイヤーを 1 つだけ選択", reply["data"]["message"])
        self.assertEqual(self.markers, [])

    def test_host_error_reaches_maya(self):
        p, events = self.driver("serve", export="ERROR")
        self.assertTrue(self.wait(lambda: any(x["app"] == "ae" for x in self.maya.peers)))
        results = []
        self.maya.request_transfer("maya2ae", {"origin": 1}, results.append)
        self.assertTrue(self.wait(lambda: results))
        self.assertEqual(results[0]["kind"], "error")
        # Localized by the panel, prefixed with the app name by the server.
        self.assertEqual(results[0]["data"]["message"],
                         "After Effects: コンポ「Comp 1」でレイヤーを 1 つだけ選択してから、もう一度送ってください（現在 0 個選択中）。")
        logs = [e["text"] for e in events if e["event"] == "log"]
        self.assertTrue(any("レイヤーを 1 つだけ選択" in t for t in logs), logs)

    def test_panel_receives_scene_settings_from_maya(self):
        # D-21: Maya's settings change the comp after the confirmation in AE.
        p, events = self.driver("serve")
        self.assertTrue(self.wait(lambda: any(x["app"] == "ae" for x in self.maya.peers)))
        results = []
        self.maya.request("settings.request", {"direction": "maya2ae", "options": {"origin": 1}}, results.append)
        self.assertTrue(self.wait(lambda: results))
        data = results[0]["data"]
        self.assertEqual(data["status"], "applied", results[0])
        self.assertTrue(data["readback"]["passed"])
        applied = [e for e in events if e["event"] == "applySettings"][0]
        self.assertAlmostEqual(applied["apply"]["duration"], 5.0)
        self.assertAlmostEqual(applied["apply"]["displayStartTime"], 1 / 24.0)
        self.assertIn(u"アニメーション範囲: 0〜95 → 1〜120", applied["message"])   # Japanese survives jsxCall

    def test_panel_requests_scene_settings_to_maya(self):
        p, events = self.driver("settings", "ae2maya")
        self.assertEqual(p.wait(30), 0, events)
        reply = [e for e in events if e["event"] == "result"][0]["reply"]
        self.assertEqual(reply["kind"], "settings.result", reply)
        self.assertEqual(reply["data"]["status"], "applied")
        self.assertEqual(self.settings_plans[0]["plan"]["apply"]["animation_range"], [1.0, 96.0])

    def test_time_slider_sync_with_maya(self):
        # D-22: AE switches it on and leads; a scrub in AE reaches Maya; Maya's time moves AE
        # and is not sent back.
        p, events = self.driver("timesync")
        self.assertTrue(self.wait(lambda: any(s["enabled"] for s in self.states)))
        self.assertTrue(self.wait(lambda: 0.0 in self.times), self.times)       # AE's time when switched on
        self.assertTrue(self.wait(lambda: 2.0 in self.times), (self.times, events))   # the scrub
        self.maya.send("time.update", {"t": 1.5})
        self.assertTrue(self.wait(lambda: any(e["event"] == "setTime" and e["t"] == 1.5 for e in events)))
        time.sleep(0.6)                                                       # a few polls later
        self.assertNotIn(1.5, self.times)
        self.maya.send("time.sync", {"enabled": False})
        self.assertTrue(self.wait(lambda: not self.states[-1]["enabled"]))

    def test_time_reads_pause_while_maya_leads(self):
        # 2026-10-23: reads every 0.05 s, but none for 0.3 s after Maya moved AE (they would queue
        # in front of setTime in AE's one-at-a-time evalScript).
        script = (
            "const C = require(%r);"
            "let now = 1000, tick = null; const calls = [];"
            "const host = {call(name, args, cb) { calls.push(name); cb(name === 'setTime' ? {time: Number(args[0])}"
            "  : {time: 0, frameDuration: 1 / 24}); }};"
            "const c = new C({host, WebSocketImpl: null, now: () => now,"
            "  setInterval: (fn, ms) => { tick = fn; return 1; }, clearInterval: () => {}});"
            "c._send = () => {};"
            "c._setTimeState({enabled: true, follow_playback: false, by: 'maya-1'});"
            "tick(); const first = calls.filter(n => n === 'compTime').length;"
            "c._applyTime(1.0); now += 100; tick();"
            "const during = calls.filter(n => n === 'compTime').length;"
            "now += C.QUIET_AFTER_SET_MS; tick();"
            "const after = calls.filter(n => n === 'compTime').length;"
            "const logs = []; c.onLog = (t) => logs.push(t);"
            "c._setTimeState({enabled: false, follow_playback: false, by: 'maya-1'});"
            "process.stdout.write(JSON.stringify([C.TIME_POLL_MS, first, during, after, logs]));"
            % os.path.join(os.path.dirname(DRIVER), "..", "..", "after_effects", "panel", "js", "sbclient.js"))
        out = subprocess.run(["node", "-e", script], capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        result = json.loads(out.stdout)
        self.assertEqual(result[:4], [50, 1, 1, 2])
        # switching off reports the measured delays (the fake host answers at once: 0 ms)
        self.assertEqual(len(result[4]), 1)
        self.assertIn(u"同期の計測（AE）: AE で時間を設定 平均 0 ms（最大 0、1 回）", result[4][0])
        self.assertIn(u"読みに行った間隔 平均 400 ms", result[4][0])

    def test_user_message_fallbacks(self):
        script = (
            "const C = require(%r);"
            "const out = ["
            "  C.userMessage({error: 'x', user: true, code: 'remap_off', params: {layer: 'L'}}),"
            "  C.userMessage({error: 'Plain English', user: true, code: 'unknown_code'}),"
            "  C.userMessage({error: 'boom', user: false}),"
            "  C.userMessage({error: 'srv', user: true, code: 'no_server'})"
            "];"
            "process.stdout.write(JSON.stringify(out));"
            % os.path.join(os.path.dirname(DRIVER), "..", "..", "after_effects", "panel", "js", "sbclient.js"))
        out = subprocess.run(["node", "-e", script], capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        messages = json.loads(out.stdout)
        self.assertEqual(messages[0], "レイヤー「L」のタイムリマップが有効になっていません。")
        self.assertEqual(messages[1], "Plain English")
        self.assertEqual(messages[2], "ExtendScript error: boom")
        self.assertIn("Connect", messages[3])

    def test_wrong_token_is_reported(self):
        p = subprocess.Popen(["node", DRIVER, str(self.port), "wrong", self.export_path, "request", "ae2maya"],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             encoding="utf-8")
        self.procs.append(p)
        out, _ = p.communicate(timeout=40)
        self.assertIn("invalid session token", out)


if __name__ == "__main__":
    unittest.main()
