"""What the hub remembers for the monitor (D-15, docs/PLATFORM_DESIGN.md 5): recent log
lines, transfer history, and a live event stream for /admin/events.
"""
from __future__ import annotations

import asyncio
import collections
import datetime
import itertools
import logging
import threading
from typing import Deque, Dict, List, Optional, Set

LOG_LINES = 2000
TRANSFERS = 200
SUBSCRIBER_QUEUE = 1000


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class EventBus:
    """Fan-out of events to /admin/events subscribers. publish() is thread safe."""

    def __init__(self):
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.subscribers: Set[asyncio.Queue] = set()

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    def publish(self, event: dict) -> None:
        loop = self.loop
        if loop is None or loop.is_closed():
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._deliver(event)
        else:
            loop.call_soon_threadsafe(self._deliver, event)

    def _deliver(self, event: dict) -> None:
        for q in list(self.subscribers):
            if q.full():                      # a slow monitor loses the oldest events, not the hub
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(event)


class LogBuffer(logging.Handler):
    """Keeps the last LOG_LINES records and publishes each one as a "log" event."""

    def __init__(self, bus: EventBus, capacity: int = LOG_LINES):
        super().__init__(level=logging.DEBUG)
        self.bus = bus
        self.records: Deque[dict] = collections.deque(maxlen=capacity)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "time": datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
        except Exception:  # never let logging break the hub
            return
        with self._lock:
            self.records.append(entry)
        self.bus.publish({"event": "log", "entry": entry})

    def tail(self, n: int) -> List[dict]:
        with self._lock:
            items = list(self.records)
        return items[-n:] if n > 0 else []


class TransferHistory:
    """The last TRANSFERS transfers: started, then finished with the outcome."""

    def __init__(self, bus: EventBus, capacity: int = TRANSFERS):
        self.bus = bus
        self.items: Deque[dict] = collections.deque(maxlen=capacity)
        self._ids = itertools.count(1)
        self._by_id: Dict[int, dict] = {}

    def start(self, requester: str, request: dict) -> dict:
        data = request.get("data", {})
        item = {
            "id": next(self._ids),
            "started": now_iso(),
            "finished": None,
            "requester": requester,
            "direction": data.get("direction"),
            "data_type": data.get("data_type", "timewarp"),
            "source": None,
            "target": None,
            "status": "running",
            "error_code": None,
            "message": None,
            "conversion_max_error": None,
            "readback_max_error": None,
            "readback_passed": None,
        }
        self.items.append(item)
        self._by_id[item["id"]] = item
        if len(self._by_id) > len(self.items):                  # forget items that fell out of the deque
            keep = {i["id"] for i in self.items}
            self._by_id = {k: v for k, v in self._by_id.items() if k in keep}
        self.bus.publish({"event": "transfer.started", "transfer": dict(item)})
        return item

    def finish(self, item: dict, result: Optional[dict] = None, error_code: Optional[str] = None,
               message: Optional[str] = None) -> None:
        item["finished"] = now_iso()
        if result is not None:
            item["status"] = result.get("status")
            item["source"] = (result.get("source") or {}).get("client_id")
            item["target"] = (result.get("target") or {}).get("client_id")
            item["message"] = result.get("message")
            conv = (result.get("report") or {}).get("conversion") or {}
            item["conversion_max_error"] = conv.get("max_error_frames")
            rb = result.get("readback") or {}
            item["readback_max_error"] = rb.get("max_error_frames")
            item["readback_passed"] = rb.get("passed")
        else:
            item["status"] = "error"
            item["error_code"] = error_code
            item["message"] = message
        self.bus.publish({"event": "transfer.finished", "transfer": dict(item)})

    def recent(self, limit: int) -> List[dict]:
        items = [dict(i) for i in self.items]
        return items[-limit:] if limit > 0 else []
