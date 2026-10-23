"""What the monitor shows, without Qt (P-B, docs/PLATFORM_DESIGN.md 5): Japanese labels and
table rows, the state of the selected hub kept up to date from /admin/events, and the event
stream itself. Standard library only, so it is unit tested without a display.
"""
from __future__ import annotations

import collections
import datetime
import json
import threading
from typing import Callable, Deque, Dict, List, Optional

from .. import hubs
from ..client.ws import WebSocket, WebSocketError

STATE_LABELS = {
    hubs.RUNNING: "正常",
    hubs.NOT_RESPONDING: "応答なし",
    hubs.STALE: "ファイルのみ（停止済み）",
    hubs.UNKNOWN: "不明（ファイルなし）",
}
APP_LABELS = {"maya": "Maya", "ae": "After Effects", "test": "テスト"}
DIRECTION_LABELS = {"maya2ae": "Maya → After Effects", "ae2maya": "After Effects → Maya"}
DATA_TYPE_LABELS = {"comp_guide": "解像度の枠", "key_markers": "キーのマーカー",
                    "scene_settings": "シーン設定"}   # "timewarp" needs no label
STATUS_LABELS = {
    "running": "実行中",
    "applied": "適用",
    "unchanged": "変更なし",
    "cancelled": "取り消し",
    "failed": "送らず（誤差が大きい）",
    "error": "エラー",
}
LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

HUB_COLUMNS = ["状態", "PID", "ポート", "バージョン", "起動", "接続", "実行ファイル"]
CLIENT_COLUMNS = ["アプリ", "ID", "文書", "バージョン", "PID", "接続時刻"]
TRANSFER_COLUMNS = ["開始", "方向", "結果", "送信元", "送信先", "変換の誤差", "読み戻し", "メッセージ"]

# Hubs before P-A (0.1.x) answer /health but have no /admin API.
NO_ADMIN_TEXT = ("ハブ PID %d（バージョン %s）は古い版で、モニターの詳細表示（アプリ・履歴・ログ）と「停止」に対応していません。"
                 "止めるには「強制終了…」を使ってください。")

MAX_TRANSFERS = 200
MAX_LOG = 2000


def local_time(iso: Optional[str], now: Optional[datetime.datetime] = None) -> str:
    """'12:34:56' for today, '10/15 12:34:56' otherwise; '' when unknown."""
    if not iso:
        return ""
    try:
        t = datetime.datetime.fromisoformat(iso).astimezone()
    except (TypeError, ValueError):
        return str(iso)
    now = now or datetime.datetime.now().astimezone()
    if t.date() == now.date():
        return t.strftime("%H:%M:%S")
    return t.strftime("%m/%d %H:%M:%S")


def _frames(value) -> str:
    return "" if value is None else "%.4f f" % value


def hub_row(hub: dict) -> List[str]:
    """hub = hubs.HubInfo.to_json()"""
    clients = hub.get("clients")
    return [
        STATE_LABELS.get(hub.get("state"), str(hub.get("state"))) + ("（使用中）" if hub.get("current") else ""),
        str(hub.get("pid", "")),
        "" if hub.get("port") is None else str(hub["port"]),
        hub.get("version") or "",
        local_time(hub.get("started")),
        "" if clients is None else str(clients),
        hub.get("image") or hub.get("executable") or "",
    ]


def client_row(client: dict) -> List[str]:
    return [
        APP_LABELS.get(client.get("app"), str(client.get("app"))),
        client.get("client_id") or "",
        client.get("document") or "",
        client.get("version") or "",
        "" if client.get("pid") is None else str(client["pid"]),
        local_time(client.get("connected_at")),
    ]


def transfer_row(item: dict) -> List[str]:
    status = STATUS_LABELS.get(item.get("status"), str(item.get("status")))
    if item.get("error_code"):
        status += "（%s）" % item["error_code"]
    passed = item.get("readback_passed")
    readback = "" if passed is None else ("合格 " if passed else "不合格 ") + _frames(item.get("readback_max_error"))
    direction = DIRECTION_LABELS.get(item.get("direction"), item.get("direction") or "")
    if item.get("data_type") in DATA_TYPE_LABELS:
        direction = "%s %s" % (DATA_TYPE_LABELS[item["data_type"]], direction)
    return [
        local_time(item.get("started")),
        direction,
        status,
        item.get("source") or "",
        item.get("target") or "",
        _frames(item.get("conversion_max_error")),
        readback.strip(),
        item.get("message") or "",
    ]


def log_line(entry: dict) -> str:
    return "%s %-7s %s  %s" % (local_time(entry.get("time")), entry.get("level", ""),
                               entry.get("logger", ""), entry.get("message", ""))


def level_passes(entry: dict, minimum: str) -> bool:
    try:
        return LEVELS.index(entry.get("level", "INFO")) >= LEVELS.index(minimum)
    except ValueError:
        return True


class HubView:
    """The selected hub: clients, transfers and log, loaded once and then kept current by events."""

    def __init__(self):
        self.status: Optional[dict] = None
        self.clients: List[dict] = []
        self.transfers: "collections.OrderedDict[int, dict]" = collections.OrderedDict()
        self.log: Deque[dict] = collections.deque(maxlen=MAX_LOG)

    def load(self, status: dict, transfers: List[dict], lines: List[dict]) -> None:
        self.status = status
        self.clients = list(status.get("clients") or [])
        self.transfers.clear()
        for item in transfers:
            self._put_transfer(item)
        self.log.clear()
        self.log.extend(lines)

    def apply(self, event: dict) -> set:
        """Update from one /admin/events message; return the parts that changed."""
        name = event.get("event")
        if name == "status":
            self.status = event["status"]
            self.clients = list(self.status.get("clients") or [])
            return {"status", "clients"}
        if name == "client.connected":
            client = event["client"]
            self.clients = [c for c in self.clients if c.get("client_id") != client.get("client_id")]
            self.clients.append(client)
            return {"clients"}
        if name == "client.disconnected":
            gone = event["client"].get("client_id")
            self.clients = [c for c in self.clients if c.get("client_id") != gone]
            return {"clients"}
        if name in ("transfer.started", "transfer.finished"):
            self._put_transfer(event["transfer"])
            return {"transfers"}
        if name == "log":
            self.log.append(event["entry"])
            return {"log"}
        return set()

    def _put_transfer(self, item: dict) -> None:
        self.transfers[item["id"]] = item
        while len(self.transfers) > MAX_TRANSFERS:
            self.transfers.popitem(last=False)

    def transfer_list(self) -> List[dict]:
        return list(self.transfers.values())


class EventStream(threading.Thread):
    """Reads /admin/events of one hub on a background thread.

    on_event(event) and on_closed(reason) are called on this thread; the Qt layer forwards
    them to the main thread with a queued signal.
    """

    def __init__(self, hub: hubs.HubInfo, on_event: Callable[[dict], None],
                 on_closed: Callable[[str], None], timeout: float = 3.0):
        super().__init__(daemon=True, name="syncbridge-monitor-events-%d" % hub.pid)
        self.hub = hub
        self.on_event = on_event
        self.on_closed = on_closed
        self.timeout = timeout
        self._conn: Optional[WebSocket] = None
        self._stopped = threading.Event()

    def run(self) -> None:
        reason = "closed"
        try:
            if not self.hub.port or not self.hub.token:
                raise WebSocketError("no port or token")
            self._conn = WebSocket.connect("127.0.0.1", self.hub.port, "/admin/events", timeout=self.timeout)
            if self._stopped.is_set():
                return
            self._conn.send_text(json.dumps({"token": self.hub.token}))
            while True:
                text = self._conn.recv()
                if text is None:
                    break
                try:
                    event = json.loads(text)
                except ValueError:
                    continue
                if event.get("event") == "error":
                    reason = event.get("message") or "error"
                    break
                self.on_event(event)
        except (OSError, WebSocketError) as exc:
            reason = str(exc)
        finally:
            if self._conn is not None:
                self._conn.close()
            if not self._stopped.is_set():
                self.on_closed(reason)

    def stop(self) -> None:
        """Close the stream; on_closed is not called afterwards."""
        self._stopped.set()
        if self._conn is not None:
            self._conn.close()


def load_hub(hub: hubs.HubInfo) -> Dict[str, object]:
    """status, transfers and log of a hub through the admin API (raises hubs.AdminError)."""
    return {
        "status": hubs.admin_call(hub, "GET", "status"),
        "transfers": hubs.admin_call(hub, "GET", "transfers?limit=%d" % MAX_TRANSFERS)["transfers"],
        "lines": hubs.admin_call(hub, "GET", "log?tail=%d" % MAX_LOG)["lines"],
    }
