"""Scene settings (D-21) and time slider sync (D-22) over the hub."""
import queue
import unittest

from syncbridge import protocol
from syncbridge.client.sync_client import SyncClient

from tests.integration.test_server import HAVE_SERVER, TOKEN, ServerFixture

MAYA = {"fps": [24, 1], "time_unit": "film", "playback_range": [11, 34], "animation_range": [1, 120],
        "pixel_aspect": 1.0, "resolution": [1920, 1080], "current_frame": 1.0}
AE = {"comp": "main", "frameRate": 24.0, "frameDuration": 1 / 24.0, "duration": 4.0, "displayStartTime": 0.0,
      "workAreaStart": 0.0, "workAreaDuration": 4.0, "pixelAspect": 1.0, "width": 1920, "height": 1080, "time": 0.0}


@unittest.skipUnless(HAVE_SERVER, "server packages not installed (requirements-server.txt)")
class SettingsFlowTest(ServerFixture):
    def connect(self, app, handlers=None, notices=None):
        c = SyncClient(app, handlers or {}, notices=notices)
        c.connect(port=self.port, token=TOKEN)
        self.addCleanup(c.disconnect)
        return c

    def app_client(self, app, settings, answer="applied", after=None):
        """A Maya / AE stand-in: reports `settings`, applies by updating them (or answers `answer`)."""
        state = {"settings": dict(settings), "applied": []}

        def export(msg):
            return {"settings": state["settings"]}

        def apply(msg):
            plan = msg["data"]["plan"]
            state["applied"].append(msg["data"])
            if answer != "applied":
                return {"status": answer}
            new = dict(state["settings"], **plan["apply"])
            if after:
                new.update(after)
            state["settings"] = new
            return {"status": "applied", "after": new, "backup": "backup.json"}
        client = self.connect(app, {"settings.export.request": export, "settings.apply.request": apply})
        return client, state

    def send(self, client, direction, items=None, origin=1):
        q = queue.Queue()
        data = {"direction": direction, "options": {"origin": origin}}
        if items is not None:
            data["items"] = items
        client.request("settings.request", data, q.put)
        return q.get(timeout=10)

    def test_maya_to_ae_from_the_maya_panel(self):
        maya, _ = self.app_client("maya", MAYA)
        _, ae = self.app_client("ae", AE)
        reply = self.send(maya, "maya2ae")
        self.assertEqual(reply["kind"], "settings.result", reply)
        data = reply["data"]
        self.assertEqual(data["status"], "applied")
        self.assertEqual(data["readback"], {"passed": True, "problems": []})
        self.assertEqual([c["item"] for c in data["changes"]], ["animation_range", "playback_range"])
        sent = ae["applied"][0]
        self.assertIn(u"アニメーション範囲: 0〜95 → 1〜120", sent["message"])
        self.assertAlmostEqual(ae["settings"]["duration"], 5.0)
        item = self.app.state.hub.history.recent(1)[0]
        self.assertEqual((item["data_type"], item["direction"], item["status"]),
                         ("scene_settings", "maya2ae", "applied"))

    def test_ae_to_maya_from_the_ae_panel(self):
        _, maya = self.app_client("maya", MAYA)
        ae, _ = self.app_client("ae", dict(AE, frameRate=30.0, frameDuration=1 / 30.0))
        reply = self.send(ae, "ae2maya", items=["fps"])
        self.assertEqual(reply["data"]["status"], "applied", reply)
        self.assertEqual(maya["applied"][0]["plan"]["apply"]["time_unit"], "ntsc")

    def test_unchanged_sends_nothing(self):
        maya, _ = self.app_client("maya", MAYA)
        _, ae = self.app_client("ae", AE)
        reply = self.send(maya, "maya2ae", items=["fps", "pixel_aspect"])
        self.assertEqual(reply["data"]["status"], "unchanged")
        self.assertEqual(ae["applied"], [])

    def test_cancelled_and_readback_failure(self):
        maya, _ = self.app_client("maya", MAYA)
        self.app_client("ae", AE, answer="cancelled")
        self.assertEqual(self.send(maya, "maya2ae")["data"]["status"], "cancelled")

    def test_readback_failure_is_reported(self):
        maya, _ = self.app_client("maya", MAYA)
        self.app_client("ae", AE, after={"workAreaStart": 0.0})
        data = self.send(maya, "maya2ae")["data"]
        self.assertFalse(data["readback"]["passed"])
        self.assertIn("workAreaStart", data["message"])

    def test_unsupported_fps_is_refused_before_maya(self):
        _, maya = self.app_client("maya", MAYA)
        ae, _ = self.app_client("ae", dict(AE, frameRate=18.0, frameDuration=1 / 18.0))
        reply = self.send(ae, "ae2maya", items=["fps"])
        self.assertEqual(reply["data"]["code"], protocol.E_CONVERSION)
        self.assertIn(u"対応していません", reply["data"]["message"])
        self.assertEqual(maya["applied"], [])

    def test_without_the_other_app(self):
        maya, _ = self.app_client("maya", MAYA)
        reply = self.send(maya, "maya2ae")
        self.assertEqual(reply["data"]["code"], protocol.E_NO_PEER)
        self.assertIn(u"After Effects が接続されていません", reply["data"]["message"])


@unittest.skipUnless(HAVE_SERVER, "server packages not installed (requirements-server.txt)")
class TimeSyncTest(ServerFixture):
    def connect(self, app):
        got = {"state": queue.Queue(), "set": queue.Queue()}
        c = SyncClient(app, {}, notices={"time.sync.state": lambda m: got["state"].put(m["data"]),
                                         "time.set": lambda m: got["set"].put(m["data"])})
        c.connect(port=self.port, token=TOKEN)
        self.addCleanup(c.disconnect)
        return c, got

    def test_state_is_shared_and_times_are_relayed(self):
        maya, maya_got = self.connect("maya")
        self.assertFalse(maya_got["state"].get(timeout=5)["enabled"])       # sent after welcome
        ae, ae_got = self.connect("ae")
        self.assertFalse(ae_got["state"].get(timeout=5)["enabled"])

        maya.send("time.update", {"t": 1.0})          # off: not relayed
        ae.send("time.sync", {"enabled": True, "follow_playback": True})
        for got in (maya_got, ae_got):
            state = got["state"].get(timeout=5)
            self.assertEqual((state["enabled"], state["follow_playback"]), (True, True))
        maya.send("time.update", {"t": 2.5})
        self.assertEqual(ae_got["set"].get(timeout=5), {"t": 2.5, "source": "maya"})
        ae.send("time.update", {"t": 0.5, "sent_at": 1761200000000.5})     # kept for measuring the delay
        self.assertEqual(maya_got["set"].get(timeout=5), {"t": 0.5, "source": "ae", "sent_at": 1761200000000.5})
        self.assertTrue(maya_got["set"].empty() and ae_got["set"].empty())   # never back to the sender

        # an app that connects later learns the state
        _, late = self.connect("maya")
        self.assertTrue(late["state"].get(timeout=5)["enabled"])

    def test_one_origin_frame(self):
        # D-38: Maya hands its scene's Origin frame to the hub, every panel gets it (also later ones),
        # and a change from AE goes to Maya
        origins = {"maya": queue.Queue(), "ae": queue.Queue(), "late": queue.Queue()}

        def client(app, key):
            c = SyncClient(app, {}, notices={"timing.state": lambda m: origins[key].put(m["data"])})
            c.connect(port=self.port, token=TOKEN)
            self.addCleanup(c.disconnect)
            return c
        maya = client("maya", "maya")
        ae = client("ae", "ae")
        maya.send("timing.set", {"origin": 1001})
        self.assertEqual(origins["ae"].get(timeout=5), {"origin": 1001.0, "by": maya.client_id})
        ae.send("timing.set", {"origin": 1009})
        self.assertEqual(origins["maya"].get(timeout=5)["origin"], 1001.0)          # its own, then AE's
        self.assertEqual(origins["maya"].get(timeout=5), {"origin": 1009.0, "by": ae.client_id})
        client("ae", "late")
        self.assertEqual(origins["late"].get(timeout=5)["origin"], 1009.0)

    def test_bad_time_is_an_error(self):
        maya, _ = self.connect("maya")
        errors = queue.Queue()
        maya.on_event = lambda name, payload: errors.put(payload) if name == "error" else None
        maya.send("time.update", {"t": "soon"})
        self.assertIn("t must be a number", errors.get(timeout=5)["message"])


if __name__ == "__main__":
    unittest.main()
