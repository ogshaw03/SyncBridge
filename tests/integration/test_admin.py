"""Admin API of the hub (P-A, docs/PLATFORM_DESIGN.md 5.3) and hub discovery (syncbridge.hubs)."""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from syncbridge import hubs
from syncbridge.server import session

from tests.integration.test_server import (HAVE_SERVER, TOKEN, ServerFixture, ae_export,
                                           maya_export)

if HAVE_SERVER:
    from websockets.sync.client import connect


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class SessionDirMixin:
    def use_temp_session_dir(self):
        self.session_dir = tempfile.mkdtemp()
        old = os.environ.get(session.ENV_DIR)
        os.environ[session.ENV_DIR] = self.session_dir

        def restore():
            if old is None:
                os.environ.pop(session.ENV_DIR, None)
            else:
                os.environ[session.ENV_DIR] = old
            shutil.rmtree(self.session_dir, ignore_errors=True)
        self.addCleanup(restore)

    def write_hub_file(self, **data):
        os.makedirs(session.hubs_dir(), exist_ok=True)
        with open(session.hub_path(data["pid"]), "w", encoding="utf-8") as f:
            json.dump(data, f)


@unittest.skipUnless(HAVE_SERVER, "server packages not installed (requirements-server.txt)")
class AdminApiTest(ServerFixture):
    def app_options(self):
        self.shutdowns = []
        return {"on_shutdown": lambda: self.shutdowns.append(1), "port": 12345}

    def call(self, method, path, token=TOKEN, header=None):
        headers = {}
        if header is not None:
            headers["Authorization"] = header
        elif token is not None:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request("http://127.0.0.1:%d/admin/%s" % (self.port, path), method=method,
                                     data=b"" if method == "POST" else None, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, None

    # -- auth ---------------------------------------------------------------------
    def test_token_is_required(self):
        for path in ("status", "transfers", "log"):
            self.assertEqual(self.call("GET", path, token=None)[0], 401, path)
            self.assertEqual(self.call("GET", path, token="wrong")[0], 401, path)
        self.assertEqual(self.call("GET", "status", header=TOKEN)[0], 401)          # no "Bearer "
        self.assertEqual(self.call("GET", "status?token=" + TOKEN, token=None)[0], 401)
        self.assertEqual(self.call("POST", "shutdown", token="wrong")[0], 401)
        self.assertEqual(self.shutdowns, [])

    # -- status / history / log ---------------------------------------------------
    def test_status_lists_clients(self):
        maya = self.client("maya", export_env=maya_export())
        code, status = self.call("GET", "status")
        self.assertEqual(code, 200)
        self.assertEqual(status["app"], "syncbridge")
        self.assertEqual(status["pid"], os.getpid())
        self.assertEqual(status["port"], 12345)
        self.assertNotIn("token", json.dumps(status))
        self.assertEqual([c["client_id"] for c in status["clients"]], [maya.client_id])
        self.assertFalse(status["transfer_running"])

    def test_transfers_are_recorded(self):
        maya = self.client("maya", export_env=maya_export())
        self.assertEqual(maya.transfer("maya2ae")["data"]["code"], "no_peer")     # no AE yet
        ae = self.client("ae", export_env=ae_export())
        self.assertEqual(maya.transfer("maya2ae")["data"]["status"], "applied")
        _, body = self.call("GET", "transfers")
        items = body["transfers"]
        self.assertEqual(len(items), 2)
        failed, applied = items
        self.assertEqual((failed["status"], failed["error_code"]), ("error", "no_peer"))
        self.assertEqual(applied["status"], "applied")
        self.assertEqual((applied["requester"], applied["source"], applied["target"]),
                         (maya.client_id, maya.client_id, ae.client_id))
        self.assertEqual(applied["direction"], "maya2ae")
        self.assertTrue(applied["readback_passed"])
        self.assertLess(applied["conversion_max_error"], 0.01)
        self.assertIsNotNone(applied["finished"])
        _, body = self.call("GET", "transfers?limit=1")
        self.assertEqual([i["id"] for i in body["transfers"]], [applied["id"]])

    def test_log_keeps_recent_lines(self):
        maya = self.client("maya", export_env=maya_export())
        self.assertTrue(self.wait_for(lambda: any(
            maya.client_id in l["message"] for l in self.call("GET", "log")[1]["lines"])))
        _, body = self.call("GET", "log?tail=1")
        self.assertEqual(len(body["lines"]), 1)
        self.assertEqual(set(body["lines"][0]), {"time", "level", "logger", "message"})

    # -- actions ------------------------------------------------------------------
    def test_shutdown_calls_back(self):
        code, body = self.call("POST", "shutdown")
        self.assertEqual((code, body["status"]), (200, "stopping"))
        self.assertTrue(self.wait_for(lambda: self.shutdowns == [1]))

    def test_disconnect_client(self):
        maya = self.client("maya", export_env=maya_export())
        self.assertEqual(self.call("POST", "clients/nobody/disconnect")[0], 404)
        code, body = self.call("POST", "clients/%s/disconnect" % maya.client_id)
        self.assertEqual((code, body["status"]), (200, "disconnected"))
        self.assertTrue(maya.closed.wait(5))
        self.assertTrue(self.wait_for(lambda: not self.app.state.manager.clients))

    # -- live events --------------------------------------------------------------
    def events(self, token=TOKEN):
        ws = connect("ws://127.0.0.1:%d/admin/events" % self.port)
        ws.send(json.dumps({"token": token}))
        self.addCleanup(ws.close)
        return ws

    def test_events_need_the_token(self):
        ws = self.events(token="wrong")
        self.assertEqual(json.loads(ws.recv(timeout=5))["event"], "error")
        with self.assertRaises(Exception):
            ws.recv(timeout=5)

    def test_events_stream(self):
        ws = self.events()
        first = json.loads(ws.recv(timeout=5))
        self.assertEqual(first["event"], "status")
        maya = self.client("maya", export_env=maya_export())
        self.client("ae", export_env=ae_export())
        maya.transfer("maya2ae")
        seen = []
        deadline = time.time() + 10
        while "transfer.finished" not in seen and time.time() < deadline:
            seen.append(json.loads(ws.recv(timeout=5))["event"])
        for name in ("client.connected", "log", "transfer.started", "transfer.finished"):
            self.assertIn(name, seen)
        self.assertLess(seen.index("transfer.started"), seen.index("transfer.finished"))


class HubDiscoveryTest(SessionDirMixin, unittest.TestCase):
    def setUp(self):
        self.use_temp_session_dir()

    def dead_pid(self):
        proc = subprocess.Popen([getattr(sys, "_base_executable", sys.executable), "-I", "-c", "pass"])
        proc.wait(10)
        return proc.pid

    def test_left_over_file_is_stale_and_can_be_removed(self):
        pid = self.dead_pid()
        self.write_hub_file(pid=pid, port=1, token="t", started=_now(), executable=sys.executable)
        found = [h for h in hubs.discover(scan_processes=False) if h.pid == pid]
        self.assertEqual(len(found), 1)
        hub = found[0]
        self.assertEqual(hub.state, hubs.STALE)
        self.assertNotIn("token", hub.to_json())
        with self.assertRaises(ValueError):
            hubs.force_kill(hub)
        self.assertTrue(hubs.remove_stale(hub))
        self.assertFalse(os.path.exists(session.hub_path(pid)))

    def test_clean_stale_files_keeps_live_hubs(self):
        # 2026-10-20: hubs stopped by force left "ファイルのみ（停止済み）" rows that piled up.
        dead = [self.dead_pid(), self.dead_pid()]
        for pid in dead:
            self.write_hub_file(pid=pid, port=1, token="t", started=_now(), executable=sys.executable)
        me = os.getpid()                               # alive: kept even though it is not a hub
        self.write_hub_file(pid=me, port=2, token="t", started=_now(), executable=sys.executable)
        with open(session.session_path(), "w", encoding="utf-8") as f:
            json.dump({"pid": dead[0], "port": 1, "token": "t"}, f)
        removed = hubs.clean_stale_files()
        self.assertEqual(sorted(removed), sorted(dead))
        self.assertEqual([d["pid"] for d in session.read_hub_files()], [me])
        self.assertIsNone(session.read_session())
        self.assertEqual(hubs.clean_stale_files(), [])

    def test_reused_pid_is_not_verified(self):
        # This test process is alive but is not the hub the file describes.
        me = os.getpid()
        image = hubs.process_image(me)
        self.write_hub_file(pid=me, port=1, token="t", started="2000-01-01T00:00:00+00:00",
                            executable=sys.executable, image=image)
        hub = [h for h in hubs.discover(scan_processes=False) if h.pid == me][0]
        if sys.platform == "win32":
            self.assertFalse(hub.verified)               # created long after "started"
            self.assertEqual(hub.state, hubs.NOT_RESPONDING)
            with self.assertRaises(ValueError):
                hubs.force_kill(hub)
        self.assertTrue(hubs.pid_alive(me))

    def test_other_program_is_not_verified(self):
        me = os.getpid()
        self.write_hub_file(pid=me, port=1, token="t", started=_now(), executable=r"C:\nowhere\SyncServer2.exe")
        hub = [h for h in hubs.discover(scan_processes=False) if h.pid == me][0]
        self.assertFalse(hub.verified)

    @unittest.skipUnless(sys.platform == "win32", "Windows process API")
    def test_force_kill_a_hung_hub(self):
        exe = getattr(sys, "_base_executable", sys.executable)
        proc = subprocess.Popen([exe, "-I", "-c", "import time; time.sleep(60)"])
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        self.write_hub_file(pid=proc.pid, port=1, token="t", started=_now(), executable=exe)
        hub = [h for h in hubs.discover(scan_processes=False) if h.pid == proc.pid][0]
        self.assertTrue(hub.verified)
        self.assertEqual(hub.state, hubs.NOT_RESPONDING)     # nothing answers on port 1
        hubs.force_kill(hub)
        self.assertEqual(proc.wait(10), 1)
        self.assertFalse(os.path.exists(session.hub_path(proc.pid)))

    def test_parse_netstat(self):
        me = os.getpid()
        text = ("\r\nActive Connections\r\n\r\n  Proto  Local Address          Foreign Address        State           PID\r\n"
                "  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1196\r\n"
                "  TCP    127.0.0.1:8765         127.0.0.1:50001        ESTABLISHED     7\r\n"
                "  TCP    127.0.0.1:8765         0.0.0.0:0              LISTENING       %d\r\n"
                "  TCP    [::]:8766              [::]:0                 LISTENING       8\r\n" % me)
        owner = hubs.parse_netstat(text, 8765)
        self.assertEqual(owner["pid"], me)
        if sys.platform == "win32":
            self.assertTrue(owner["name"].lower().startswith("python"))
        self.assertEqual(hubs.parse_netstat(text, 8766)["pid"], 8)
        self.assertIsNone(hubs.parse_netstat(text, 9999))

    def test_process_helpers_on_this_process(self):
        self.assertTrue(hubs.pid_alive(os.getpid()))
        self.assertFalse(hubs.pid_alive(0))
        if sys.platform == "win32":
            self.assertTrue(os.path.isfile(hubs.process_image(os.getpid())))
            created = hubs.process_create_time(os.getpid())
            self.assertLess(abs(time.time() - created), 3600)
            self.assertIsInstance(hubs.list_server_processes(), list)


@unittest.skipUnless(HAVE_SERVER, "server packages not installed (requirements-server.txt)")
class RunningHubTest(SessionDirMixin, ServerFixture):
    """A hub in this process that wrote its files like __main__ does."""

    def setUp(self):
        self.use_temp_session_dir()
        super().setUp()
        session.write_session(self.port, TOKEN, "test")
        self.addCleanup(session.remove_session)

    def test_write_session_records_the_hub(self):
        data = session.read_hub_files()
        self.assertEqual([d["pid"] for d in data], [os.getpid()])
        self.assertEqual(data[0]["port"], self.port)
        self.assertEqual(data[0]["executable"], sys.executable)
        self.assertEqual(session.read_session()["pid"], os.getpid())

    def test_discover_and_admin_call(self):
        hub = [h for h in hubs.discover(scan_processes=False) if h.pid == os.getpid()][0]
        self.assertTrue(hub.current)
        if sys.platform == "win32":
            self.assertTrue(hub.verified, hub.to_json())
            self.assertEqual(hub.state, hubs.RUNNING)
        status = hubs.admin_call(hub, "GET", "status")
        self.assertEqual(status["pid"], os.getpid())
        hub.token = "wrong"
        with self.assertRaises(hubs.AdminError) as ctx:
            hubs.admin_call(hub, "GET", "status")
        self.assertEqual(ctx.exception.status, 401)

    def test_remove_session_removes_both_files(self):
        session.remove_session()
        self.assertEqual(session.read_hub_files(), [])
        self.assertIsNone(session.read_session())


if __name__ == "__main__":
    unittest.main()
