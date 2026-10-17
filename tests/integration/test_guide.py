"""Comp guide over the hub (D-16): guide.request -> Maya -> guide.result, and its history."""
import queue
import unittest

from syncbridge import protocol
from syncbridge.client.sync_client import SyncClient

from tests.integration.test_server import HAVE_SERVER, TOKEN, ServerFixture

COMP = {"name": "main", "width": 1920, "height": 1080, "pixelAspect": 1}


@unittest.skipUnless(HAVE_SERVER, "server packages not installed (requirements-server.txt)")
class GuideFlowTest(ServerFixture):
    def connect(self, app, handlers=None):
        c = SyncClient(app, handlers or {})
        c.connect(port=self.port, token=TOKEN)
        self.addCleanup(c.disconnect)
        return c

    def send(self, client, comp, **extra):
        q = queue.Queue()
        client._request("guide.request", dict({"comp": comp}, **extra), q.put)
        return q.get(timeout=10)

    def maya(self, reply=None, fail=None):
        self.received = []

        def handle(msg):
            self.received.append(msg["data"]["guide"])
            if fail:
                raise RuntimeError(fail)
            return reply or {"status": "applied", "camera": "shotCam", "render": [2112, 1188],
                             "comp": [1920, 1080], "warnings": ["w1"]}
        return self.connect("maya", {"guide.apply.request": handle})

    def test_guide_reaches_maya_and_is_recorded(self):
        maya = self.maya()
        ae = self.connect("ae")
        reply = self.send(ae, COMP)
        self.assertEqual(reply["kind"], "guide.result", reply)
        data = reply["data"]
        self.assertEqual((data["status"], data["camera"], data["message"]), ("applied", "shotCam", "w1"))
        self.assertEqual((data["source"]["client_id"], data["target"]["client_id"]), (ae.client_id, maya.client_id))
        self.assertEqual(self.received, [{"name": "main", "width": 1920, "height": 1080, "pixelAspect": 1.0}])
        item = self.app.state.hub.history.recent(1)[0]
        self.assertEqual((item["data_type"], item["direction"], item["status"]), ("comp_guide", "ae2maya", "applied"))

    def test_without_maya(self):
        ae = self.connect("ae")
        reply = self.send(ae, COMP)
        self.assertEqual(reply["data"]["code"], protocol.E_NO_PEER)
        self.assertIn("Maya が接続されていません", reply["data"]["message"])
        self.assertEqual(self.app.state.hub.history.recent(1)[0]["status"], "error")

    def test_bad_comp_is_refused_before_maya(self):
        self.maya()
        ae = self.connect("ae")
        reply = self.send(ae, {"width": 0, "height": 1080})
        self.assertEqual(reply["data"]["code"], protocol.E_BAD_MESSAGE)
        self.assertEqual(self.received, [])

    def test_maya_error_is_forwarded(self):
        self.maya(fail=u"カメラのビューが見つかりません")
        ae = self.connect("ae")
        reply = self.send(ae, COMP)
        self.assertEqual(reply["kind"], "error")
        self.assertIn(u"カメラのビューが見つかりません", reply["data"]["message"])


if __name__ == "__main__":
    unittest.main()
