"""Live sync of AE layers to Maya (D-41): the hub's shared switch and relay, and the AE panel's watching
(a change is sent once the layer stops changing). The AE panel part runs sbclient.js in Node."""
import json
import os
import queue
import shutil
import subprocess
import unittest

from syncbridge import protocol
from syncbridge.client.sync_client import SyncClient

from tests.integration.test_server import HAVE_SERVER, TOKEN, ServerFixture

BG = {"comp_id": 30, "comp": "camera", "layer_id": 5, "layer": "BG",
      "via": [{"comp_id": 30, "comp": "camera", "layer_id": 2, "layer": "Comp 1"}]}
CHA = {"comp_id": 30, "comp": "camera", "layer_id": 6, "layer": "CHA", "via": []}


class LiveProtocolTest(unittest.TestCase):
    def test_messages_are_checked(self):
        ok = protocol.decode(protocol.encode(protocol.message("live.changed", {"layers": [BG]})))
        self.assertEqual(ok["data"]["layers"], [BG])
        for kind, data in (("live.sync", {"enabled": "yes"}), ("live.watch", {"layers": "BG"}),
                           ("live.changed", {"layers": [1]}), ("live.sync.state", {"enabled": True})):
            with self.assertRaises(protocol.ProtocolError):
                protocol.decode(protocol.encode(protocol.message(kind, data)))


@unittest.skipUnless(HAVE_SERVER, "server packages not installed (requirements-server.txt)")
class LiveSyncHubTest(ServerFixture):
    def connect(self, app):
        got = {"state": queue.Queue(), "changed": queue.Queue()}
        c = SyncClient(app, {}, notices={"live.sync.state": lambda m: got["state"].put(m["data"]),
                                         "live.changed": lambda m: got["changed"].put(m["data"])})
        c.connect(port=self.port, token=TOKEN)
        self.addCleanup(c.disconnect)
        return c, got

    def test_switch_watch_list_and_changes(self):
        maya, maya_got = self.connect("maya")
        self.assertEqual(maya_got["state"].get(timeout=5)["enabled"], False)      # sent after welcome
        ae, ae_got = self.connect("ae")
        ae_got["state"].get(timeout=5)

        ae.send("live.changed", {"layers": [BG]})              # off: not relayed
        ae.send("live.sync", {"enabled": True})                 # the switch is shared
        for got in (maya_got, ae_got):
            self.assertTrue(got["state"].get(timeout=5)["enabled"])
        maya.send("live.watch", {"layers": [BG, CHA]})          # Maya says what to watch
        state = ae_got["state"].get(timeout=5)
        self.assertEqual((state["enabled"], state["layers"]), (True, [BG, CHA]))
        maya_got["state"].get(timeout=5)

        ae.send("live.changed", {"layers": [CHA]})
        self.assertEqual(maya_got["changed"].get(timeout=5), {"layers": [CHA], "source": "ae"})
        self.assertTrue(maya_got["changed"].empty() and ae_got["changed"].empty())   # only to Maya, only once

        maya.send("live.sync", {"enabled": False})
        self.assertFalse(ae_got["state"].get(timeout=5)["enabled"])
        ae.send("live.changed", {"layers": [CHA]})
        with self.assertRaises(queue.Empty):
            maya_got["changed"].get(timeout=0.5)

        maya.send("live.sync", {"enabled": True})
        maya_got["state"].get(timeout=5)
        _, late = self.connect("ae")       # a panel that connects later learns it (it replaces `ae`: last)
        state = late["state"].get(timeout=5)
        self.assertEqual((state["enabled"], state["layers"]), (True, [BG, CHA]))


PANEL_SCRIPT = r"""
const path = require('path');
const SBPanelClient = require(path.join(process.argv[1], 'after_effects', 'panel', 'js', 'sbclient.js'));
const prints = JSON.parse(process.argv[2]);       // what AE answers on each read: [[BG, CHA], ...]
let read = 0;
const sent = [];
const host = { call(name, args, cb) {
    if (name !== 'layersFingerprint') { throw new Error(name); }
    const asked = JSON.parse(args[0]).layers.map((l) => l.layer);
    cb({ prints: prints[Math.min(read++, prints.length - 1)].slice(0, asked.length) });
} };
const c = new SBPanelClient({ host: host, setInterval: () => 1, clearInterval: () => {}, onLog: () => {} });
c._send = (msg) => sent.push([msg.kind, msg.data.layers.map((l) => l.layer)]);
c._setLiveState({ enabled: true, layers: JSON.parse(process.argv[3]) });
for (let i = 0; i < prints.length; i++) { c._pollLive(); }
process.stdout.write(JSON.stringify(sent));
"""


@unittest.skipUnless(shutil.which("node"), "needs Node")
class PanelWatchTest(unittest.TestCase):
    """sbclient.js: the first read is the starting point; a change goes out when the next read shows
    the same again (done dragging), once; a layer AE cannot find (null) is never sent."""

    def run_panel(self, prints, layers=(BG, CHA)):
        root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
        out = subprocess.run(["node", "-e", PANEL_SCRIPT, root, json.dumps(prints), json.dumps(list(layers))],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_sent_once_after_the_drag(self):
        prints = [["a", "c"],               # starting point
                  ["a1", "c"],              # dragging BG
                  ["a2", "c"],
                  ["a2", "c"],              # stopped: BG goes to Maya
                  ["a2", "c"],              # not again
                  ["a2", "c2"], ["a2", "c2"]]   # CHA changed, then stopped
        self.assertEqual(self.run_panel(prints), [["live.changed", ["BG"]], ["live.changed", ["CHA"]]])

    def test_nothing_for_a_missing_layer_or_no_change(self):
        self.assertEqual(self.run_panel([["a", None], ["a", None], ["a", None]]), [])
        self.assertEqual(self.run_panel([["a", "c"], ["b", "d"], ["b", "d"]]),
                         [["live.changed", ["BG", "CHA"]]])          # both stopped on the same read: one message


if __name__ == "__main__":
    unittest.main()
