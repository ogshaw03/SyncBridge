"""Local Sync Server end to end, with fake Maya / AE clients over real WebSockets.

Needs the server packages (requirements-server.txt); skipped without them so
the stdlib-only test run (and Maya's Python) still works.
"""
import asyncio
import os
import queue
import shutil
import tempfile
import threading
import time
import unittest

try:
    import uvicorn
    from websockets.sync.client import connect
    from syncbridge.server.app import create_app
    HAVE_SERVER = True
except ImportError:
    HAVE_SERVER = False

from syncbridge import protocol
from syncbridge.core import ae_codec, envelope, maya_codec, testcurves
from syncbridge.server import session

TOKEN = "test-token"
ORIGIN = 1.0 / 24.0   # Maya frame 1 <-> comp 0 s


def maya_export(curve=None, playback=(1, 97)):
    curve = (curve or testcurves.speed_ramp_bezier()).affine(in_offset=ORIGIN, out_offset=ORIGIN)
    return envelope.make("maya.timewarp.export", {
        "curve_node": "timewarp", "native": maya_codec.encode(curve, [24, 1]), "samples": None,
        "scene": {"fps": [24, 1], "playback_range": list(playback)}}, "maya")


def ae_export(keys=None):
    keys = keys if keys is not None else ae_codec.encode(testcurves.slowmo_linear())
    return envelope.make("ae.timeremap.export", {
        "comp": {"frameRate": 24.0, "frameDuration": 1 / 24.0, "duration": 4.0},
        "layer": {"name": "src", "startTime": 0.0, "stretch": 100}, "keys": keys,
        "samples": _ae_samples(keys)}, "ae")


def _ae_samples(keys):
    curve = ae_codec.decode(keys)
    times = [i / 96.0 for i in range(4 * 96 + 1)]
    return {"times": times, "values": [curve.evaluate(t) for t in times]}


def _maya_after(native):
    """What a perfect Maya returns after applying `native`: an export with Maya-evaluated samples."""
    curve = maya_codec.decode(native)
    frames = [1 + i / 4.0 for i in range(4 * 96 + 1)]
    values = [curve.evaluate(f / 24.0) * 24.0 for f in frames]
    return envelope.make("maya.timewarp.export", {
        "native": native, "samples": {"times": frames, "values": values},
        "scene": {"fps": [24, 1]}}, "maya")


class FakeApp:
    """A Maya or AE stand-in: answers export/apply requests, can send transfer requests."""

    def __init__(self, url, app, export_env=None, apply_mode="apply", token=TOKEN):
        self.app = app
        self.export_env = export_env
        self.apply_mode = apply_mode           # apply | cancel | error | hang | slow
        self.apply_requests = []
        self.peers = []
        self.release = threading.Event()
        self._replies = {}
        self._lock = threading.Lock()
        self.ws = connect(url)
        self.ws.send(protocol.encode(protocol.message(
            "hello", {"token": token, "app": app, "version": "test", "pid": os.getpid(),
                      "document": "%s-doc" % app}, app)))
        self.welcome = protocol.decode(self.ws.recv(timeout=5))
        self.closed = threading.Event()
        if self.welcome["kind"] == "welcome":
            self.client_id = self.welcome["data"]["client_id"]
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def _loop(self):
        try:
            for text in self.ws:
                msg = protocol.decode(text)
                kind = msg["kind"]
                if msg.get("reply_to"):
                    with self._lock:
                        q = self._replies.get(msg["reply_to"])
                    if q is not None:
                        q.put(msg)
                        continue
                if kind == "peers":
                    self.peers = msg["data"]["clients"]
                elif kind == "export.request":
                    self.ws.send(protocol.encode(protocol.reply(msg, {"export": self.export_env}, self.app)))
                elif kind == "apply.request":
                    # Like the real apps, the confirmation must not block receiving.
                    threading.Thread(target=self._apply, args=(msg,), daemon=True).start()
        except Exception:
            pass
        finally:
            self.closed.set()

    def _apply(self, msg):
        self.apply_requests.append(msg)
        apply_env = msg["data"]["apply"]
        if self.apply_mode == "hang":
            return
        if self.apply_mode == "slow":
            self.release.wait(10)
        if self.apply_mode == "error":
            self.ws.send(protocol.encode(protocol.error(protocol.E_APP, "boom", self.app, msg["event_id"])))
            return
        if self.apply_mode == "cancel":
            self.ws.send(protocol.encode(protocol.reply(msg, {"status": "cancelled"}, self.app)))
            return
        if self.app == "ae":
            keys = apply_env["data"]["keys"]
            after = ae_export(keys)
        else:
            after = _maya_after(apply_env["data"]["native"])
        self.ws.send(protocol.encode(protocol.reply(
            msg, {"status": "applied", "after": after, "backup": "/tmp/backup.json"}, self.app)))

    def transfer(self, direction, options=None, timeout=20, **extra):
        data = dict({"direction": direction, "options": options or {"origin": 1}}, **extra)
        msg = protocol.message("transfer.request", data, self.app)
        q = queue.Queue()
        with self._lock:
            self._replies[msg["event_id"]] = q
        self.ws.send(protocol.encode(msg))
        return q.get(timeout=timeout)

    def close(self):
        self.ws.close()


class ServerFixture(unittest.TestCase):
    """A real server on a free port, plus FakeApp helpers. Contains no tests itself."""
    def setUp(self):
        self.app = create_app(TOKEN, export_timeout=5, apply_timeout=5)
        config = uvicorn.Config(self.app, host="127.0.0.1", port=0, log_level="warning", ws="websockets-sansio")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        deadline = time.time() + 10
        while not self.server.started and time.time() < deadline:
            time.sleep(0.02)
        self.port = self.server.servers[0].sockets[0].getsockname()[1]
        self.url = "ws://127.0.0.1:%d%s" % (self.port, protocol.WS_PATH)
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            try:
                c.close()
            except Exception:
                pass
        self.server.should_exit = True
        self.thread.join(10)

    def client(self, app, **kw):
        c = FakeApp(self.url, app, **kw)
        self.clients.append(c)
        return c

    def wait_for(self, predicate, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return True
            time.sleep(0.02)
        return False



@unittest.skipUnless(HAVE_SERVER, "server packages not installed (requirements-server.txt)")
class ServerTest(ServerFixture):
    # -- session / auth ---------------------------------------------------------
    def test_health_and_probe(self):
        info = session.probe_server(self.port)
        self.assertEqual(info["app"], "syncbridge")
        self.assertNotIn("token", info)
        self.assertTrue(session.port_in_use(self.port))

    def test_wrong_token_is_rejected(self):
        c = self.client("maya", token="wrong")
        self.assertEqual(c.welcome["kind"], "error")
        self.assertEqual(c.welcome["data"]["code"], protocol.E_AUTH)
        self.assertEqual(len(self.app.state.manager.clients), 0)

    def test_first_message_must_be_hello(self):
        ws = connect(self.url)
        ws.send(protocol.encode(protocol.message("transfer.request", {"direction": "maya2ae"})))
        reply = protocol.decode(ws.recv(timeout=5))
        self.assertEqual(reply["data"]["code"], protocol.E_BAD_MESSAGE)
        ws.close()

    def test_peers_are_broadcast(self):
        maya = self.client("maya", export_env=maya_export())
        ae = self.client("ae", export_env=ae_export())
        self.assertTrue(self.wait_for(lambda: len(maya.peers) == 2))
        self.assertEqual(sorted(p["app"] for p in maya.peers), ["ae", "maya"])
        ae.close()
        self.assertTrue(self.wait_for(lambda: len(maya.peers) == 1))

    # -- transfers --------------------------------------------------------------
    def test_maya_to_ae(self):
        maya = self.client("maya", export_env=maya_export())
        ae = self.client("ae", export_env=ae_export())
        result = maya.transfer("maya2ae")
        self.assertEqual(result["kind"], "transfer.result", result)
        data = result["data"]
        self.assertEqual(data["status"], "applied")
        self.assertTrue(data["report"]["conversion"]["passed"])
        self.assertTrue(data["readback"]["passed"])
        self.assertEqual(data["target"]["client_id"], ae.client_id)
        self.assertEqual(len(ae.apply_requests), 1)
        sent = ae.apply_requests[0]["data"]["apply"]
        self.assertEqual(sent["kind"], "ae.timeremap.apply")
        # Maya frame 1 -> comp 0 s (origin option)
        self.assertAlmostEqual(sent["data"]["keys"][0]["time"], 0.0, places=9)

    def test_ae_to_maya_requested_from_ae(self):
        maya = self.client("maya", export_env=maya_export())
        ae = self.client("ae", export_env=ae_export())
        result = ae.transfer("ae2maya")
        data = result["data"]
        self.assertEqual(data["status"], "applied", data)
        self.assertTrue(data["readback"]["passed"])
        native = maya.apply_requests[0]["data"]["apply"]["data"]["native"]
        self.assertEqual(native["keys"][0]["time"], 1.0)   # comp 0 s -> Maya frame 1

    def test_pull_direction_from_the_target(self):
        # Maya asks for AE -> Maya: source is the AE client, target is Maya itself.
        maya = self.client("maya", export_env=maya_export())
        self.client("ae", export_env=ae_export())
        self.assertEqual(maya.transfer("ae2maya")["data"]["status"], "applied")
        self.assertEqual(len(maya.apply_requests), 1)

    def test_cancel_is_reported(self):
        maya = self.client("maya", export_env=maya_export())
        self.client("ae", export_env=ae_export(), apply_mode="cancel")
        data = maya.transfer("maya2ae")["data"]
        self.assertEqual(data["status"], "cancelled")
        self.assertNotIn("readback", data)

    def test_no_peer(self):
        maya = self.client("maya", export_env=maya_export())
        reply = maya.transfer("maya2ae")
        self.assertEqual(reply["kind"], "error")
        self.assertEqual(reply["data"]["code"], protocol.E_NO_PEER)

    def test_app_error_is_forwarded(self):
        maya = self.client("maya", export_env=maya_export())
        self.client("ae", export_env=ae_export(), apply_mode="error")
        reply = maya.transfer("maya2ae")
        self.assertEqual(reply["kind"], "error")
        self.assertIn("boom", reply["data"]["message"])

    def test_target_disconnect_during_apply(self):
        maya = self.client("maya", export_env=maya_export())
        ae = self.client("ae", export_env=ae_export(), apply_mode="hang")
        threading.Timer(0.5, ae.close).start()
        reply = maya.transfer("maya2ae")
        self.assertEqual(reply["data"]["code"], protocol.E_DISCONNECTED)

    def test_apply_timeout(self):
        maya = self.client("maya", export_env=maya_export())
        self.client("ae", export_env=ae_export(), apply_mode="hang")
        reply = maya.transfer("maya2ae", timeout=15)
        self.assertEqual(reply["data"]["code"], protocol.E_TIMEOUT)

    def test_failed_conversion_is_not_applied(self):
        # Sloped linear infinity over a wider playback range cannot be kept in Editable mode (R-20).
        maya = self.client("maya", export_env=maya_export(testcurves.linear_infinity(), playback=(1, 121)))
        ae = self.client("ae", export_env=ae_export())
        data = maya.transfer("maya2ae")["data"]
        self.assertEqual(data["status"], "failed")
        self.assertFalse(data["report"]["conversion"]["passed"])
        self.assertEqual(ae.apply_requests, [])

    def test_maya_to_ae_target_without_time_remap(self):
        # V-P1C: the selected AE layer had Time Remap off; it is still a valid target.
        off = ae_export()
        off["data"]["keys"], off["data"]["samples"] = [], None
        maya = self.client("maya", export_env=maya_export())
        ae = self.client("ae", export_env=off)
        data = maya.transfer("maya2ae")["data"]
        self.assertEqual(data["status"], "applied", data)
        self.assertEqual(len(ae.apply_requests), 1)

    def test_ae_to_maya_without_time_remap_is_refused(self):
        off = ae_export()
        off["data"]["keys"], off["data"]["samples"] = [], None
        maya = self.client("maya", export_env=maya_export())
        ae = self.client("ae", export_env=off)
        reply = ae.transfer("ae2maya")
        self.assertEqual(reply["kind"], "error")
        self.assertEqual(reply["data"]["code"], protocol.E_CONVERSION)
        self.assertIn("has no Time Remap to send", reply["data"]["message"])
        self.assertEqual(maya.apply_requests, [])

    def test_new_connection_from_same_process_replaces_old_one(self):
        # V-P1C: reloading the Maya modules left the old connection open; transfers went to it.
        old = self.client("maya", export_env=maya_export())
        ae = self.client("ae", export_env=ae_export())
        self.assertTrue(self.wait_for(lambda: len(ae.peers) == 2))
        new = self.client("maya", export_env=maya_export())     # same pid (this test process)
        self.assertTrue(old.closed.wait(5), "the old connection was not closed")
        self.assertTrue(self.wait_for(lambda: [p["client_id"] for p in ae.peers if p["app"] == "maya"]
                                      == [new.client_id]))
        self.assertEqual(ae.transfer("ae2maya")["data"]["status"], "applied")
        self.assertEqual(len(new.apply_requests), 1)
        self.assertEqual(old.apply_requests, [])

    def test_source_too_short_is_refused_before_apply(self):
        # 0.1.0 on AE 26.5: "setValueAtTime ... value 7.26 is out of range 0 to 2" (R-16).
        short = ae_export()
        short["data"]["layer"]["source"] = {"name": "src", "duration": 2.0, "frameRate": 24.0}
        maya = self.client("maya", export_env=maya_export())     # speed ramp reaches 6 s of source
        ae = self.client("ae", export_env=short)
        reply = maya.transfer("maya2ae")
        self.assertEqual(reply["kind"], "error")
        self.assertEqual(reply["data"]["code"], protocol.E_CONVERSION)
        self.assertIn("素材は 2.00 秒（48 フレーム）", reply["data"]["message"])
        self.assertIn("何も変更していません", reply["data"]["message"])
        self.assertEqual(ae.apply_requests, [])

    def test_source_long_enough_is_applied(self):
        long_enough = ae_export()
        long_enough["data"]["layer"]["source"] = {"name": "src", "duration": 10.0, "frameRate": 24.0}
        maya = self.client("maya", export_env=maya_export())
        self.client("ae", export_env=long_enough)
        self.assertEqual(maya.transfer("maya2ae")["data"]["status"], "applied")

    def test_bad_options(self):
        maya = self.client("maya", export_env=maya_export())
        self.client("ae", export_env=ae_export())
        reply = maya.transfer("maya2ae", options={"mode": "fast"})
        self.assertEqual(reply["data"]["code"], protocol.E_BAD_MESSAGE)

    def test_second_transfer_while_busy(self):
        maya = self.client("maya", export_env=maya_export())
        ae = self.client("ae", export_env=ae_export(), apply_mode="slow")
        first = {}
        t = threading.Thread(target=lambda: first.update(r=maya.transfer("maya2ae")))
        t.start()
        self.assertTrue(self.wait_for(lambda: len(ae.apply_requests) == 1))
        second = ae.transfer("ae2maya")
        self.assertEqual(second["data"]["code"], protocol.E_BUSY)
        ae.release.set()
        t.join(10)
        self.assertEqual(first["r"]["data"]["status"], "applied")


class SessionFileTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.old = os.environ.get(session.ENV_DIR)
        os.environ[session.ENV_DIR] = self.dir

    def tearDown(self):
        if self.old is None:
            os.environ.pop(session.ENV_DIR, None)
        else:
            os.environ[session.ENV_DIR] = self.old
        shutil.rmtree(self.dir)

    def test_write_read_remove(self):
        token = session.new_token()
        self.assertGreaterEqual(len(token), 40)
        session.write_session(8765, token, "0.0.1")
        data = session.read_session()
        self.assertEqual((data["port"], data["token"], data["pid"]), (8765, token, os.getpid()))
        session.remove_session(pid=os.getpid() + 1)      # someone else's file is kept
        self.assertIsNotNone(session.read_session())
        session.remove_session()
        self.assertIsNone(session.read_session())

    def test_no_server_on_free_port(self):
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.assertIsNone(session.probe_server(port, timeout=0.5))


@unittest.skipUnless(HAVE_SERVER, "server packages not installed (requirements-server.txt)")
class IdleWatchTest(unittest.TestCase):
    def test_idle_callback_fires_when_nobody_is_connected(self):
        from syncbridge.server.app import _idle_watch
        from syncbridge.server.connections import ConnectionManager
        manager = ConnectionManager()
        fired = []
        asyncio.run(asyncio.wait_for(_idle_watch(manager, 0.2, lambda: fired.append(1)), 5))
        self.assertEqual(fired, [1])


if __name__ == "__main__":
    unittest.main()
