"""Monitor labels, rows and the selected-hub state (P-B), without Qt."""
import datetime
import unittest

from syncbridge import hubs
from syncbridge.monitor import model


def _transfer(i, status="running", **kw):
    item = {"id": i, "started": "2026-10-16T03:00:00+00:00", "finished": None, "requester": "maya-1",
            "direction": "maya2ae", "data_type": "timewarp", "source": None, "target": None,
            "status": status, "error_code": None, "message": None, "conversion_max_error": None,
            "readback_max_error": None, "readback_passed": None}
    item.update(kw)
    return item


class LabelTest(unittest.TestCase):
    def test_local_time(self):
        now = datetime.datetime(2026, 10, 16, 12, 0, tzinfo=datetime.timezone.utc).astimezone()
        same_day = now.replace(hour=now.hour, minute=1, second=2)
        self.assertEqual(model.local_time(same_day.isoformat(), now), same_day.strftime("%H:%M:%S"))
        other = now - datetime.timedelta(days=3)
        self.assertEqual(model.local_time(other.isoformat(), now), other.strftime("%m/%d %H:%M:%S"))
        self.assertEqual(model.local_time(None), "")
        self.assertEqual(model.local_time("garbage"), "garbage")

    def test_hub_row(self):
        row = model.hub_row({"state": hubs.RUNNING, "current": True, "pid": 12, "port": 8765,
                             "version": "0.1.1", "started": None, "clients": 2, "image": r"C:\x\SyncServer.exe"})
        self.assertEqual(row[0], "正常（使用中）")
        self.assertEqual(row[1:4], ["12", "8765", "0.1.1"])
        self.assertEqual(row[5:], ["2", r"C:\x\SyncServer.exe"])
        stale = model.hub_row({"state": hubs.STALE, "pid": 3, "port": None, "clients": None})
        self.assertEqual(stale[0], "ファイルのみ（停止済み）")
        self.assertEqual((stale[2], stale[5]), ("", ""))
        self.assertEqual(len(row), len(model.HUB_COLUMNS))

    def test_client_row(self):
        row = model.client_row({"client_id": "ae-2", "app": "ae", "version": "0.1.1", "pid": 5,
                                "document": "comp.aep", "connected_at": None})
        self.assertEqual(row[:5], ["After Effects", "ae-2", "comp.aep", "0.1.1", "5"])
        self.assertEqual(len(row), len(model.CLIENT_COLUMNS))

    def test_transfer_row(self):
        ok = model.transfer_row(_transfer(1, "applied", source="maya-1", target="ae-2",
                                          conversion_max_error=0.0, readback_max_error=0.00012,
                                          readback_passed=True))
        self.assertEqual(ok[1:5], ["Maya → After Effects", "適用", "maya-1", "ae-2"])
        self.assertEqual(ok[5:7], ["0.0000 f", "合格 0.0001 f"])
        err = model.transfer_row(_transfer(2, "error", error_code="no_peer", message="no ae"))
        self.assertEqual(err[2], "エラー（no_peer）")
        self.assertEqual((err[5], err[6], err[7]), ("", "", "no ae"))
        self.assertEqual(len(ok), len(model.TRANSFER_COLUMNS))

    def test_log_levels(self):
        self.assertTrue(model.level_passes({"level": "WARNING"}, "INFO"))
        self.assertFalse(model.level_passes({"level": "DEBUG"}, "INFO"))
        self.assertTrue(model.level_passes({"level": "ODD"}, "ERROR"))
        line = model.log_line({"time": None, "level": "INFO", "logger": "syncbridge.server", "message": "hi"})
        self.assertIn("syncbridge.server  hi", line)


class HubViewTest(unittest.TestCase):
    def setUp(self):
        self.view = model.HubView()
        self.view.load({"clients": [{"client_id": "maya-1", "app": "maya"}]},
                       [_transfer(1, "applied")], [{"level": "INFO", "message": "a"}])

    def test_clients_follow_events(self):
        self.assertEqual(self.view.apply({"event": "client.connected", "client": {"client_id": "ae-2"}}),
                         {"clients"})
        self.view.apply({"event": "client.connected", "client": {"client_id": "ae-2", "document": "x"}})
        self.assertEqual([c["client_id"] for c in self.view.clients], ["maya-1", "ae-2"])
        self.assertEqual(self.view.clients[1]["document"], "x")
        self.view.apply({"event": "client.disconnected", "client": {"client_id": "maya-1"}})
        self.assertEqual([c["client_id"] for c in self.view.clients], ["ae-2"])

    def test_transfers_are_updated_in_place(self):
        self.view.apply({"event": "transfer.started", "transfer": _transfer(2)})
        self.view.apply({"event": "transfer.finished", "transfer": _transfer(2, "cancelled")})
        self.assertEqual([(t["id"], t["status"]) for t in self.view.transfer_list()],
                         [(1, "applied"), (2, "cancelled")])

    def test_transfers_are_capped(self):
        for i in range(2, model.MAX_TRANSFERS + 10):
            self.view.apply({"event": "transfer.started", "transfer": _transfer(i)})
        items = self.view.transfer_list()
        self.assertEqual(len(items), model.MAX_TRANSFERS)
        self.assertEqual(items[-1]["id"], model.MAX_TRANSFERS + 9)

    def test_log_and_status_and_unknown(self):
        self.assertEqual(self.view.apply({"event": "log", "entry": {"message": "b"}}), {"log"})
        self.assertEqual([e["message"] for e in self.view.log], ["a", "b"])
        self.view.apply({"event": "status", "status": {"clients": []}})
        self.assertEqual(self.view.clients, [])
        self.assertEqual(self.view.apply({"event": "future.kind"}), set())


if __name__ == "__main__":
    unittest.main()
