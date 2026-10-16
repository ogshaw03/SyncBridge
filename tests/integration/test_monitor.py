"""Monitor against a real hub (P-B): the event stream, the hub's log file and stop notice,
and the window itself (offscreen Qt; skipped without PySide6)."""
import json
import os
import queue
import tempfile
import threading
import time
import unittest

from syncbridge import hubs, protocol
from syncbridge.monitor import model
from syncbridge.server import session

from tests.integration.test_admin import SessionDirMixin
from tests.integration.test_server import HAVE_SERVER, TOKEN, ServerFixture, ae_export, maya_export

if HAVE_SERVER:
    from websockets.sync.client import connect

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


def _hub(port, token=TOKEN):
    return hubs.HubInfo(os.getpid(), port=port, token=token)


@unittest.skipUnless(HAVE_SERVER, "server packages not installed (requirements-server.txt)")
class EventStreamTest(ServerFixture):
    def app_options(self):
        self.log_file = os.path.join(tempfile.mkdtemp(), "hub.log")
        self.shutdowns = []
        return {"log_file": self.log_file, "on_shutdown": lambda: self.shutdowns.append(1)}

    def stream(self, token=TOKEN):
        events, closed = queue.Queue(), queue.Queue()
        s = model.EventStream(_hub(self.port, token), events.put, closed.put)
        s.start()
        self.addCleanup(s.stop)
        return s, events, closed

    def next_event(self, events, name, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            e = events.get(timeout=max(0.01, deadline - time.time()))
            if e["event"] == name:
                return e
        raise AssertionError("no %s event" % name)

    def test_events_reach_the_view(self):
        _s, events, _closed = self.stream()
        view = model.HubView()
        view.apply(self.next_event(events, "status"))
        maya = self.client("maya", export_env=maya_export())
        self.client("ae", export_env=ae_export())
        view.apply(self.next_event(events, "client.connected"))
        view.apply(self.next_event(events, "client.connected"))
        self.assertEqual({c["app"] for c in view.clients}, {"maya", "ae"})
        maya.transfer("maya2ae")
        view.apply(self.next_event(events, "transfer.finished"))
        self.assertEqual(view.transfer_list()[-1]["status"], "applied")

    def test_wrong_token_closes_the_stream(self):
        _s, _events, closed = self.stream(token="wrong")
        self.assertEqual(closed.get(timeout=5), "invalid token")

    def test_stop_does_not_report_closed(self):
        s, events, closed = self.stream()
        self.next_event(events, "status")
        s.stop()
        s.join(5)
        self.assertFalse(s.is_alive())
        self.assertTrue(closed.empty())

    def test_load_hub(self):
        self.client("maya", export_env=maya_export())
        data = model.load_hub(_hub(self.port))
        self.assertEqual(len(data["status"]["clients"]), 1)
        self.assertEqual(data["transfers"], [])
        self.assertTrue(data["lines"])

    def test_log_file_gets_the_lines(self):
        maya = self.client("maya", export_env=maya_export())
        def written():
            with open(self.log_file, encoding="utf-8") as f:
                return "connected %s" % maya.client_id in f.read()
        self.assertTrue(self.wait_for(written))

    def test_shutdown_tells_the_apps(self):
        ws = connect(self.url)
        ws.send(protocol.encode(protocol.message("hello", {"token": TOKEN, "app": "maya", "pid": 1}, "maya")))
        self.assertEqual(protocol.decode(ws.recv(timeout=5))["kind"], "welcome")
        hubs.admin_call(_hub(self.port), "POST", "shutdown")
        codes = []
        deadline = time.time() + 5
        while protocol.E_HUB_STOPPING not in codes and time.time() < deadline:
            msg = protocol.decode(ws.recv(timeout=5))
            if msg["kind"] == "error":
                codes.append(msg["data"]["code"])
                self.assertIn("停止", msg["data"]["message"])
        self.assertIn(protocol.E_HUB_STOPPING, codes)
        ws.close()


@unittest.skipUnless(HAVE_SERVER and HAVE_QT, "needs the server packages and PySide6 (requirements-monitor.txt)")
class MonitorWindowTest(SessionDirMixin, ServerFixture):
    """The window finds the hub of this process and shows its clients and transfers."""

    @classmethod
    def setUpClass(cls):
        cls.qapp = QApplication.instance() or QApplication([])

    def setUp(self):
        self.use_temp_session_dir()
        super().setUp()
        session.write_session(self.port, TOKEN, "test")
        self.addCleanup(session.remove_session)

    def pump(self, predicate, timeout=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.qapp.processEvents()
            if predicate():
                return True
            time.sleep(0.02)
        return False

    def test_window_shows_the_hub(self):
        from syncbridge.monitor.window import MonitorWindow
        maya = self.client("maya", export_env=maya_export())
        w = MonitorWindow()
        self.addCleanup(w.close)
        # Other SyncServer.exe processes on this PC are listed too (process scan): look for ours.
        mine = str(os.getpid())
        self.assertTrue(self.pump(lambda: any(w.hub_table.item(r, 1).text() == mine
                                              for r in range(w.hub_table.rowCount()))))
        self.assertEqual(w.selected, os.getpid())        # the current hub is selected first
        self.assertTrue(self.pump(lambda: w.client_table.rowCount() == 1))
        self.assertTrue(w.stop_btn.isEnabled())
        self.assertTrue(self.pump(lambda: w.stream is not None))
        self.client("ae", export_env=ae_export())
        self.assertTrue(self.pump(lambda: w.client_table.rowCount() == 2))
        maya.transfer("maya2ae")
        self.assertTrue(self.pump(lambda: w.transfer_table.rowCount() == 1
                                  and w.transfer_table.item(0, 2).text() == "適用"))
        self.assertIn("connected", w.log_text.toPlainText())
        self.assertFalse(w.clean_btn.isEnabled())

    def test_hub_without_admin_api(self):
        # V-P-B: the installed 0.1.1 SyncServer.exe answers /health but /admin is 404.
        from syncbridge.monitor.window import MonitorWindow
        w = MonitorWindow()
        self.addCleanup(w.close)
        self.assertTrue(self.pump(lambda: w.stream is not None))
        w.stream.stop()
        w.stream = None
        w._on_hub_loaded(os.getpid(), hubs.AdminError(404, "Not Found"))
        self.assertIn("古い版", w.detail.text())
        self.assertFalse(w.stop_btn.isEnabled())
        w.refresh()                       # stays disabled after the list is rebuilt
        self.assertTrue(self.pump(lambda: not w._discovering))
        self.assertFalse(w.stop_btn.isEnabled())


if __name__ == "__main__":
    unittest.main()
