"""Time slider sync between Maya and the active AE comp (Phase 2, D-22).

Messages carry `t` = AE comp time in seconds. Maya converts with its frame rate and the
origin frame of its SyncBridge panel (the same mapping as a transfer):

    t = (frame - origin) / fps          frame = origin + t * fps

AE sends and applies comp.time as it is. Pure, standard library only (used by the Maya
adapter and by tests).
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from .timebase import FrameRate

SEND_INTERVAL = 1.0 / 30.0      # seconds between two updates sent while scrubbing
FRAME_SNAP = 1e-4               # frames: a time this close to a whole frame is that frame


def maya_frame_to_time(frame: float, maya_fps, origin: float) -> float:
    return (float(frame) - float(origin)) / FrameRate(maya_fps).fps


def time_to_maya_frame(t: float, maya_fps, origin: float) -> float:
    frame = float(origin) + float(t) * FrameRate(maya_fps).fps
    rounded = round(frame)
    return float(rounded) if abs(frame - rounded) < FRAME_SNAP else frame


class Throttle:
    """At most one send per `interval` seconds; the last value is sent once the interval is over.

        if throttle.offer(value): send(value)        # now
        ... later: value = throttle.due()            # the held value, when its time has come
    """

    def __init__(self, interval: float = SEND_INTERVAL, clock: Callable[[], float] = time.monotonic):
        self.interval = interval
        self.clock = clock
        self._last_sent: Optional[float] = None
        self._held = None
        self._has_held = False

    def offer(self, value) -> bool:
        now = self.clock()
        if self._last_sent is None or now - self._last_sent >= self.interval:
            self._last_sent = now
            self._has_held = False
            return True
        self._held, self._has_held = value, True
        return False

    def wait(self) -> float:
        """Seconds until the held value may be sent (0 when nothing is held)."""
        if not self._has_held or self._last_sent is None:
            return 0.0
        return max(0.0, self.interval - (self.clock() - self._last_sent))

    def due(self):
        """The held value if its time has come (and forget it), else None."""
        if self._has_held and self.wait() <= 0.0:
            self._has_held = False
            self._last_sent = self.clock()
            return self._held
        return None


class LatencyStats:
    """Delays measured while the sync is on (milliseconds), summed up when it is switched off.

    Maya, the hub and AE run on the same PC, so `sent_at` (epoch ms) of one app can be compared
    with the clock of the other (2026-10-23: the user felt a lag in both directions)."""

    LABELS = (
        ("recv", u"受け取るまで"),
        ("apply", u"Maya で時間を設定"),
    )

    def __init__(self, keep: int = 500):
        self.keep = keep
        self.values = {}

    def add(self, name: str, ms: float) -> None:
        values = self.values.setdefault(name, [])
        values.append(float(ms))
        del values[:-self.keep]

    def summary(self) -> str:
        """'受け取るまで 平均 12 ms（最大 40、25 回）、…' or '' when nothing was measured."""
        parts = []
        for name, label in self.LABELS:
            values = self.values.get(name)
            if values:
                parts.append(u"%s 平均 %d ms（最大 %d、%d 回）" % (
                    label, round(sum(values) / len(values)), round(max(values)), len(values)))
        return u"、".join(parts)

    def clear(self) -> None:
        self.values = {}


def now_ms() -> float:
    return time.time() * 1000.0


class EchoGuard:
    """Recognizes the time change caused by applying a received time, so it is not sent back."""

    def __init__(self, tolerance: float = 1e-3):
        self.tolerance = tolerance
        self._applied: Optional[float] = None

    def applied(self, value: float) -> None:
        self._applied = float(value)

    def is_echo(self, value: float) -> bool:
        """True once for the value that was applied last."""
        if self._applied is not None and abs(float(value) - self._applied) <= self.tolerance:
            self._applied = None
            return True
        return False
