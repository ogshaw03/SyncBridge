"""SyncClient (the stdlib client used inside Maya) against the real server.

The Maya main thread is emulated by a queue that the test pumps: everything
the client hands to `dispatch` must run there, like maya.utils.executeDeferred.
"""
import os
import queue
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest

from syncbridge import protocol
from syncbridge.client import launcher
from syncbridge.client.sync_client import ConnectError, SyncClient
from syncbridge.core import envelope
from syncbridge.server import session

from .test_server import HAVE_SERVER, TOKEN, ServerFixture, _maya_after, ae_export, maya_export


class MainThread:
    """Stand-in for Maya's main thread (executeDeferred)."""

    def __init__(self):
        self.q = queue.Queue()
        self.ran_on = []

    def dispatch(self, fn):
        self.q.put(fn)

    def pump(self, until, timeout=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if until():
                return True
            try:
                fn = self.q.get(timeout=0.05)
            except queue.Empty:
                continue
            self.ran_on.append(threading.current_thread().name)
            fn()
        return until()


@unittest.skipUnless(HAVE_SERVER, "server packages not installed (requirements-server.txt)")
class SyncClientTest(ServerFixture):
    """A real server (ServerFixture) with a SyncClient acting as Maya."""

    def setUp(self):
        super().setUp()
        self.session_dir = tempfile.mkdtemp()
        self.old_env = os.environ.get(session.ENV_DIR)
        os.environ[session.ENV_DIR] = self.session_dir
        session.write_session(self.port, TOKEN, "test")
        self.main = MainThread()
        self.events = []
        self.applied = []
        self.maya = None

    def tearDown(self):
        if self.maya is not None:
            self.maya.disconnect()
        if self.old_env is None:
            os.environ.pop(session.ENV_DIR, None)
        else:
            os.environ[session.ENV_DIR] = self.old_env
        shutil.rmtree(self.session_dir)
        super().tearDown()

    def make_maya(self, export_env=None, apply_handler=None):
        def export_handler(msg):
            self.assertEqual(threading.current_thread().name, "MainThread")
            return {"export": export_env or maya_export()}

        def default_apply(msg):
            apply_env = msg["data"]["apply"]
            self.applied.append(apply_env)
            return {"status": "applied", "after": _maya_after(apply_env["data"]["native"]),
                    "backup": "backup.json"}

        self.maya = SyncClient("maya", {"export.request": export_handler,
                                        "apply.request": apply_handler or default_apply},
                               dispatch=self.main.dispatch,
                               on_event=lambda name, payload: self.events.append((name, payload)),
                               document=lambda: "shot010.mb")
        return self.maya

    def test_connect_with_session_file(self):
        welcome = self.make_maya().connect()
        self.assertTrue(welcome["client_id"].startswith("maya-"))
        self.assertTrue(self.maya.connected)
        self.assertTrue(self.main.pump(lambda: any(e[0] == "peers" for e in self.events)))
        self.assertEqual(self.maya.peers[0]["document"], "shot010.mb")

    def test_wrong_token(self):
        with self.assertRaises(ConnectError) as ctx:
            self.make_maya().connect(token="wrong")
        self.assertIn("invalid session token", str(ctx.exception))

    def test_no_session(self):
        os.remove(session.session_path())
        with self.assertRaises(ConnectError):
            self.make_maya().connect()

    def test_maya_to_ae_from_the_client(self):
        self.make_maya().connect()
        ae = self.client("ae", export_env=ae_export())
        results = []
        self.maya.request_transfer("maya2ae", {"origin": 1}, results.append)
        self.assertTrue(self.main.pump(lambda: results))
        self.assertEqual(results[0]["kind"], "transfer.result", results[0])
        self.assertEqual(results[0]["data"]["status"], "applied")
        self.assertTrue(results[0]["data"]["readback"]["passed"])
        self.assertEqual(len(ae.apply_requests), 1)
        # Requests and callbacks ran on the emulated main thread only.
        self.assertTrue(self.main.ran_on and set(self.main.ran_on) == {"MainThread"})

    def test_ae_to_maya_applies_on_main_thread(self):
        self.make_maya().connect()
        ae = self.client("ae", export_env=ae_export())
        result = {}
        t = threading.Thread(target=lambda: result.update(r=ae.transfer("ae2maya")))
        t.start()
        self.assertTrue(self.main.pump(lambda: not t.is_alive()))
        self.assertEqual(result["r"]["data"]["status"], "applied", result["r"])
        self.assertEqual(len(self.applied), 1)
        self.assertIn(("request", "apply.request"), self.events)

    def test_handler_error_reaches_the_requester(self):
        def broken(msg):
            raise RuntimeError("No Scene Time Warp curve")
        self.make_maya(apply_handler=broken).connect()
        ae = self.client("ae", export_env=ae_export())
        result = {}
        t = threading.Thread(target=lambda: result.update(r=ae.transfer("ae2maya")))
        t.start()
        self.assertTrue(self.main.pump(lambda: not t.is_alive()))
        self.assertEqual(result["r"]["kind"], "error")
        self.assertIn("No Scene Time Warp", result["r"]["data"]["message"])

    def test_disconnect_fails_pending_requests(self):
        self.make_maya().connect()
        self.client("ae", export_env=ae_export(), apply_mode="hang")
        results = []
        self.maya.request_transfer("maya2ae", {"origin": 1}, results.append)
        self.assertTrue(self.main.pump(lambda: self.app.state.flow._lock.locked()))
        time.sleep(0.3)   # let the server reach the apply step
        self.server.should_exit = True     # server goes away
        self.assertTrue(self.main.pump(lambda: results, timeout=15))
        self.assertEqual(results[0]["kind"], "error")
        self.assertTrue(self.main.pump(lambda: any(e[0] == "disconnected" for e in self.events)))
        self.assertFalse(self.maya.connected)


class LauncherTest(unittest.TestCase):
    def test_env_drops_host_python_settings(self):
        env = launcher.server_env({"PYTHONHOME": "C:/maya/Python", "PYTHONPATH": "C:/maya/site",
                                   "PATH": "x"}, root="R")
        self.assertNotIn("PYTHONHOME", env)
        self.assertEqual(env["PYTHONPATH"], os.path.join("R", "src"))
        self.assertEqual(env["PATH"], "x")

    def test_repo_root(self):
        self.assertTrue(os.path.isfile(os.path.join(launcher.repo_root(), "src", "syncbridge", "__init__.py")))

    def test_installed_exe_is_preferred(self):
        tmp = tempfile.mkdtemp()
        exe = os.path.join(tmp, launcher.SERVER_EXE)
        open(exe, "w").close()
        old = os.environ.get(launcher.ENV_SERVER_EXE)
        os.environ[launcher.ENV_SERVER_EXE] = exe
        try:
            argv, env, cwd = launcher.server_command()
            self.assertEqual(argv, [exe])
            self.assertEqual(cwd, tmp)
            self.assertNotIn("PYTHONHOME", env)
        finally:
            if old is None:
                os.environ.pop(launcher.ENV_SERVER_EXE, None)
            else:
                os.environ[launcher.ENV_SERVER_EXE] = old
            shutil.rmtree(tmp)

    def test_development_fallback(self):
        argv, env, cwd = launcher.server_command(python=sys.executable)
        self.assertEqual(argv[1:], ["-m", "syncbridge.server"])
        self.assertEqual(env["PYTHONPATH"], os.path.join(launcher.repo_root(), "src"))

    def test_missing_python(self):
        port = _free_port()
        with self.assertRaises(RuntimeError):
            launcher.ensure_server(port, python=os.path.join(tempfile.gettempdir(), "no-such-python.exe"))

    @unittest.skipUnless(HAVE_SERVER, "server packages not installed (requirements-server.txt)")
    def test_starts_a_server_once(self):
        tmp = tempfile.mkdtemp()
        old = os.environ.get(session.ENV_DIR)
        os.environ[session.ENV_DIR] = tmp
        port = _free_port()
        try:
            info = launcher.ensure_server(port, python=sys.executable, idle_timeout=5, wait=30)
            self.assertEqual(info["app"], "syncbridge")
            first_pid = session.read_session()["pid"]
            again = launcher.ensure_server(port, python=sys.executable)   # already running: no second server
            self.assertEqual(again["app"], "syncbridge")
            self.assertEqual(session.read_session()["pid"], first_pid)
            c = SyncClient("test")
            c.connect()
            self.assertTrue(c.connected)
            c.disconnect()
            # idle timeout (5 s) stops it and removes the session file
            deadline = time.time() + 30
            while time.time() < deadline and session.probe_server(port, timeout=0.3):
                time.sleep(0.5)
            self.assertIsNone(session.probe_server(port, timeout=0.3))
        finally:
            if old is None:
                os.environ.pop(session.ENV_DIR, None)
            else:
                os.environ[session.ENV_DIR] = old
            shutil.rmtree(tmp, ignore_errors=True)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


if __name__ == "__main__":
    unittest.main()
