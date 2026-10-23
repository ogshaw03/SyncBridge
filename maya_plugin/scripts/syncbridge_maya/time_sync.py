"""Time slider sync, Maya side (D-22).

While the shared switch is on (time.sync.state from the hub):
  * Maya's time changes (timeChanged) are sent as time.update {t}, at most 30 per second
    while scrubbing; during playback only when "follow playback" is on, otherwise the frame
    where playback stops (the playingBack condition) is sent.
  * time.set {t} from AE moves Maya's current time; the resulting time change is not sent back.
t = AE comp time = (frame - origin) / fps, origin = the Origin frame of the SyncBridge panel.

Not yet run in the GUI (H-MY-29): MEventMessage "timeChanged" and MConditionMessage
"playingBack" while scrubbing / playing, cmds.play(q=True, state=True) during playback.
Must be used on Maya's main thread.
"""
from __future__ import annotations

import threading
from typing import Callable, List, Optional

import maya.utils
from maya import cmds

from syncbridge.core import time_sync
from syncbridge.core.timebase import FrameRate


def _fps() -> FrameRate:
    return FrameRate.from_maya_unit(cmds.currentUnit(q=True, time=True))


def _playing() -> bool:
    return bool(cmds.play(q=True, state=True))


class MayaTimeSync:
    def __init__(self, send: Callable[[float], bool]):
        self.send = send                      # send(t) -> sent?
        self.enabled = False
        self.follow_playback = False
        self.origin = 1.0
        self.throttle = time_sync.Throttle()
        self.echo = time_sync.EchoGuard()
        self.stats = time_sync.LatencyStats()
        self.last_summary = ""
        self._callbacks: List[int] = []
        self._timer: Optional[threading.Timer] = None
        self._last_sent: Optional[float] = None

    # -- switch ---------------------------------------------------------------------
    def set_state(self, enabled: bool, follow_playback: bool = False) -> None:
        self.follow_playback = bool(follow_playback)
        if bool(enabled) == self.enabled:
            return
        self.enabled = bool(enabled)
        if self.enabled:
            import maya.api.OpenMaya as om          # here: the tests' stand-in Maya has no maya.api
            self._callbacks.append(om.MEventMessage.addEventCallback("timeChanged", self._on_time))
            self._callbacks.append(om.MConditionMessage.addConditionCallback("playingBack", self._on_playing))
        else:
            self.stop()

    def stop(self) -> None:
        summary = self.stats.summary()
        if summary:
            print("SyncBridge time sync (Maya): %s" % summary)
            self.last_summary = summary
        self.stats.clear()
        self.enabled = False
        if self._callbacks:
            import maya.api.OpenMaya as om
        for callback_id in self._callbacks:
            try:
                om.MMessage.removeCallback(callback_id)
            except RuntimeError:
                pass
        self._callbacks = []
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self._last_sent = None

    # -- Maya -> AE -------------------------------------------------------------------
    def current_time(self) -> float:
        return time_sync.maya_frame_to_time(cmds.currentTime(q=True), _fps(), self.origin)

    def push_current(self) -> None:
        """Send Maya's time now (the panel that switched the sync on leads)."""
        self._send(self.current_time())

    def _on_time(self, *_args) -> None:
        try:
            frame = cmds.currentTime(q=True)
            if self.echo.is_echo(frame):
                return
            if not self.follow_playback and _playing():
                return
            self._offer(time_sync.maya_frame_to_time(frame, _fps(), self.origin))
        except Exception as exc:      # never break Maya's time changes
            print("SyncBridge time sync: %s" % exc)

    def _on_playing(self, playing, *_args) -> None:
        if not playing and self.enabled:
            self._send(self.current_time())        # where playback stopped

    def _offer(self, t: float) -> None:
        if self._last_sent is not None and abs(t - self._last_sent) < 1e-9:
            return
        if self.throttle.offer(t):
            self._send(t)
        else:
            self._schedule()

    def _schedule(self) -> None:
        """Send the held time once the interval is over (the last scrub position is never lost)."""
        if self._timer is None:
            self._timer = threading.Timer(self.throttle.wait(), lambda: maya.utils.executeDeferred(self._flush))
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        self._timer = None
        if not self.enabled:
            return
        t = self.throttle.due()
        if t is not None:
            self._send(t)
        elif self.throttle.wait() > 0:
            self._schedule()

    def _send(self, t: float) -> None:
        self._last_sent = t
        self.send(t)

    # -- AE -> Maya ---------------------------------------------------------------------
    def apply_time(self, t: float, sent_at: Optional[float] = None) -> None:
        if not self.enabled or _playing():
            return                              # do not fight Maya's own playback
        start = time_sync.now_ms()
        if sent_at:
            self.stats.add("recv", start - float(sent_at))     # AE read it -> Maya's main thread has it
        frame = time_sync.time_to_maya_frame(t, _fps(), self.origin)
        if abs(frame - cmds.currentTime(q=True)) < 1e-6:
            return
        self.echo.applied(frame)
        self._last_sent = float(t)
        cmds.currentTime(frame, update=True)
        self.stats.add("apply", time_sync.now_ms() - start)
