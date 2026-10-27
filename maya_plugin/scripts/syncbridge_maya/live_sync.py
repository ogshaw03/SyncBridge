"""Live sync of AE layers to Maya (D-41), Maya side.

While the shared switch is on (live.sync.state from the hub), Maya tells the AE panel which AE layers to
watch: the AE layers of the links that can be transferred (live.watch). When the user is done changing one
in AE, the panel sends live.changed; Maya reads the layer's motion over the playback range again
(motion.request, like "transfer the animation") and keys the link's dedicated camera without asking.

Safety (development rules 2 and "no automatic overwrite on a conflict"):
  * only the links' cameras (the dedicated cameras, D-29) are keyed, as by the transfer;
  * each update is one undo ("SyncBridge live"); the keys replaced the first time are backed up;
  * keys that changed in Maya since the live sync wrote them (an edit, an undo) are not overwritten:
    that link is skipped with a warning until the live sync is switched on again.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from syncbridge.core import layer_mapping as core_lm

state = {"enabled": False, "by": None, "layers": []}
_written: Dict[str, Dict[str, list]] = {}   # mapping id -> {attr key: [[frame, value], ...]} last written
_backed_up = set()                          # mapping ids backed up since the switch went on
_queue: List[tuple] = []                    # AE layer keys to update
_busy = False
_last_watch: Optional[list] = None
_warned = set()
TOLERANCE = 1e-6


def _service():
    from . import service
    return service


def watch_list(store: dict) -> List[dict]:
    """The AE layers of the transferable links (once each), as the AE panel finds them."""
    from . import motion
    links, _skipped = motion.transferable(store)
    out, seen = [], set()
    for m in links:
        key = core_lm.ae_key(m["ae"])
        if key not in seen:
            seen.add(key)
            ae = m["ae"]
            out.append({"comp_id": ae.get("comp_id"), "comp": ae.get("comp"), "layer_id": ae.get("layer_id"),
                        "layer": ae.get("layer"), "via": list(ae.get("via") or [])})
    return out


def publish_watch(force: bool = False) -> None:
    """Tell the hub (and the AE panel) which AE layers to watch, when it changed."""
    global _last_watch
    svc = _service()
    if not state["enabled"] or not svc.is_connected():
        return
    from . import layer_mapping
    try:
        layers = watch_list(layer_mapping.store())
    except Exception as exc:
        print("SyncBridge: live sync: %s" % exc)
        return
    if force or layers != _last_watch:
        _last_watch = layers
        svc.client().send("live.watch", {"layers": layers})


def on_state(msg: dict) -> None:
    """live.sync.state from the hub: switched on / off, or the watch list changed."""
    global _last_watch
    data = msg["data"]
    was_on = state["enabled"]
    state.update(enabled=bool(data["enabled"]), by=data.get("by"), layers=list(data.get("layers") or []))
    if state["enabled"] and not was_on:
        reset()
        publish_watch(force=True)
    if not state["enabled"]:
        _last_watch = None
        del _queue[:]
    _service()._notify("live_sync", dict(state))


def reset() -> None:
    """A fresh start (switched on, another scene): AE's state may overwrite again."""
    _written.clear()
    _backed_up.clear()
    _warned.clear()


def on_changed(msg: dict) -> None:
    """live.changed from AE: queue the layers and update their links' cameras one after another."""
    if not state["enabled"]:
        return
    for layer in msg["data"].get("layers") or []:
        key = core_lm.ae_key(layer)
        if key not in _queue:
            _queue.append(key)
    _next()


def _say(text: str, error: bool = False) -> None:
    print("SyncBridge: %s" % text)
    _service()._notify("live_applied", {"text": text, "error": error})


def _changed_in_maya(p: dict) -> List[str]:
    """Attributes whose keys are not what the live sync wrote last (an edit or an undo in Maya)."""
    from . import motion
    before = _written.get(p["mapping_id"])
    if before is None:
        return []
    from maya import cmds
    out = []
    for key, points in before.items():
        plug = motion._plug(p["camera"], key)
        for frame, value in points:
            if abs(cmds.getAttr(plug, time=frame) - value) > TOLERANCE:
                out.append(plug.split(".")[-1])
                break
    return out


def _next() -> None:
    global _busy
    if _busy or not _queue or not state["enabled"]:
        return
    from . import layer_mapping, motion, timing
    key = _queue.pop(0)
    store = layer_mapping.store()
    links, skipped = motion.transferable(store)
    links = [m for m in links if core_lm.ae_key(m["ae"]) == key]
    if not links:
        reason = [s for s in skipped if s]
        if reason and key not in _warned:
            _warned.add(key)
            _say(u"リアルタイム同期: 反映できない接続があります（%s）" % u" ".join(reason), error=True)
        _next()
        return
    start, end = timing.playback_range()
    origin = timing.origin()
    _busy = True
    _run(links, start, end, origin)


def _run(links: List[dict], start: float, end: float, origin: float) -> None:
    from . import motion
    svc = _service()
    link, rest = links[0], links[1:]

    def finish():
        global _busy
        if rest:
            _run(rest, start, end, origin)
            return
        _busy = False
        _next()

    try:
        q = motion.query(link["id"], start, end, origin)
    except Exception as exc:
        _say(u"リアルタイム同期: %s: %s" % (link["ae"].get("layer"), exc), error=True)
        finish()
        return

    def done(reply):
        name = link["ae"].get("layer")
        try:
            if not state["enabled"]:
                return
            if reply["kind"] == "error":
                _say(u"リアルタイム同期: %s を AE から読めませんでした（%s）" % (name, reply["data"].get("message")),
                     error=True)
                return
            p = motion.plan(link["id"], q["frames"], reply["data"])
            changed = _changed_in_maya(p)
            if changed:
                if link["id"] not in _warned:
                    _warned.add(link["id"])
                    _say(u"リアルタイム同期: %s のカメラ %s のキー（%s）が Maya で変わっているので、上書きしませんでした。"
                         u"AE の状態で上書きするときは、リアルタイム同期をオンにし直してください。"
                         % (name, motion.camera_label(p["camera"]), u"、".join(changed)), error=True)
                return
            first = link["id"] not in _backed_up
            result = motion.apply_all([p], confirm=False, backup=first, chunk="SyncBridge live")[0]
            _backed_up.add(link["id"])
            _written[link["id"]] = {k: [list(x) for x in v] for k, v in p["keys"].items()}
            _say(u"リアルタイム同期: %s → %s（%g〜%g フレーム、誤差 最大 %.3f px%s）" % (
                name, motion.camera_label(p["camera"]), result["frames"][0], result["frames"][1],
                result["max_error_px"], u"" if result["readback"]["passed"] else u"、読み戻し不一致"),
                error=not result["readback"]["passed"])
        except Exception as exc:
            _say(u"リアルタイム同期: %s: %s" % (name, exc), error=True)
        finally:
            finish()

    try:
        svc.request_ae_motion(q["request"], done)
    except Exception as exc:
        _say(u"リアルタイム同期: %s: %s" % (link["ae"].get("layer"), exc), error=True)
        finish()
