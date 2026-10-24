"""Pixel Mapping over the hub (D-24): pixelmap.request -> Maya -> pixelmap.result, and its history."""
import queue
import unittest

from syncbridge import protocol
from syncbridge.client.sync_client import SyncClient

from tests.integration.test_server import HAVE_SERVER, TOKEN, ServerFixture

INFO = {"comp": {"id": 12, "name": "c010", "width": 1920, "height": 1080, "pixelAspect": 1, "time": 0.5},
        "layer": {"id": 345, "name": "BG", "position": [1000.25, 500.5], "anchorPoint": [3000, 2000],
                  "scale": [100, 100], "rotation": 0, "threeD": False, "parent": None, "effects": [],
                  "source": "bg.png", "source_width": 6000, "source_height": 4000}}


@unittest.skipUnless(HAVE_SERVER, "server packages not installed (requirements-server.txt)")
class PixelMapFlowTest(ServerFixture):
    def connect(self, app, handlers=None):
        c = SyncClient(app, handlers or {})
        c.connect(port=self.port, token=TOKEN)
        self.addCleanup(c.disconnect)
        return c

    def maya(self):
        self.received = []

        def handle(msg):
            self.received.append(msg["data"])
            return {"status": "applied", "mapping": {"id": "vl-1", "name": "BG"}, "values": {"hfo": -0.0295},
                    "max_error_px": 1e-9, "warnings": []}
        return self.connect("maya", {"pixelmap.apply.request": handle})

    def send(self, client, info, options=None):
        q = queue.Queue()
        client.request("pixelmap.request", {"info": info, "options": options or {}}, q.put)
        return q.get(timeout=10)

    def test_reaches_maya_and_is_recorded(self):
        maya = self.maya()
        ae = self.connect("ae")
        reply = self.send(ae, INFO, {"method": "film_offset"})
        self.assertEqual(reply["kind"], "pixelmap.result", reply)
        self.assertEqual((reply["data"]["status"], reply["data"]["target"]["client_id"]), ("applied", maya.client_id))
        self.assertEqual(self.received[0]["info"]["layer"]["position"], [1000.25, 500.5])
        self.assertEqual(self.received[0]["options"], {"method": "film_offset"})
        item = self.app.state.hub.history.recent(1)[0]
        self.assertEqual((item["data_type"], item["direction"], item["status"]), ("pixel_mapping", "ae2maya", "applied"))

    def test_bad_info_is_refused_before_maya(self):
        self.maya()
        ae = self.connect("ae")
        bad = {"comp": INFO["comp"], "layer": dict(INFO["layer"], position=None)}
        reply = self.send(ae, bad)
        self.assertEqual(reply["data"]["code"], protocol.E_BAD_MESSAGE)
        self.assertEqual(self.received, [])

    def test_without_maya(self):
        ae = self.connect("ae")
        reply = self.send(ae, INFO)
        self.assertEqual(reply["data"]["code"], protocol.E_NO_PEER)


if __name__ == "__main__":
    unittest.main()
