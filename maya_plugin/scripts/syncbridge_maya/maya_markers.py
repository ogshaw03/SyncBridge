"""Markers made in Maya alone (D-55): the keys of one attribute shown as Time Slider Bookmarks.

    add(frame) / remove(frame)        a key on SB_MARKERS.marker (one undo each; the node is made if needed)
    select_node()                     the node selected: the Time Slider shows its keys, which can be dragged
    frames()                          the key frames, in order
    watch()                           follow the keys (the panel on open, the plug-in after a scene is opened)
    export() / set_frames(frames)     for a later sync with AE: the markers with their comp times / keys set again

The keys are the data: they are keyed, moved and deleted with Maya's own tools (S, the Time Slider, the Graph
Editor) and undone like any key. The bookmarks are made from them (tagged syncBridgeMayaMarker, not in the
undo queue, saved with the scene so they show in a Maya without SyncBridge), and the AE markers' bookmarks
(key_markers, D-18) are left alone.

A key change is followed by the API: the anim curve's dirty callback fires on every key added, moved, deleted
or undone, and on a time change too; the node's attribute-changed callback when the curve is connected or goes
(mayapy 2023, H-MY-50). The bookmarks are made again, deferred, only when the frames changed.
"""
from __future__ import annotations

from typing import Callable, List, Optional

from maya import cmds

from syncbridge.core import markers as core_markers

from . import comp_guide

NODE = "SB_MARKERS"
ATTR = "marker"
MARK_ATTR = "syncBridgeMarkers"          # on the node: made by SyncBridge
TAG_ATTR = "syncBridgeMayaMarker"        # on our bookmarks (the AE markers' have syncBridgeMarker)
BOOKMARK_PLUGIN = "timeSliderBookmark"
BOOKMARK_COLOR = (0.35, 0.85, 1.0)       # cyan: the AE markers are orange
NEAR = 0.5                               # frames: remove() takes the key this close
STATE_KEY = "_syncbridge_maya_markers"   # in __main__: callbacks survive the SB Dev reload of this module

listeners: List[Callable[[List[float]], None]] = []      # the panel's label, called after each update


def _state() -> dict:
    import __main__
    state = getattr(__main__, STATE_KEY, None)
    if state is None:
        state = {"callbacks": [], "pending": False, "frames": None}
        setattr(__main__, STATE_KEY, state)
    return state


def exists() -> bool:
    return cmds.objExists(NODE) and cmds.attributeQuery(ATTR, node=NODE, exists=True)


def frames() -> List[float]:
    if not exists():
        return []
    return sorted(cmds.keyframe("%s.%s" % (NODE, ATTR), q=True, timeChange=True) or [])


def _make_node() -> str:
    """A transform with one keyable attribute: S keys only it, the Time Slider shows only its keys."""
    node = cmds.createNode("transform", name=NODE, skipSelect=True)
    cmds.addAttr(node, longName=MARK_ATTR, attributeType="bool", defaultValue=True)
    cmds.setAttr("%s.%s" % (node, MARK_ATTR), lock=True)
    cmds.addAttr(node, longName=ATTR, niceName=u"Marker", attributeType="double", keyable=True)
    for attr in ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ",
                 "scaleX", "scaleY", "scaleZ", "visibility"):
        cmds.setAttr("%s.%s" % (node, attr), lock=True, keyable=False, channelBox=False)
    return node


def add(frame: Optional[float] = None) -> float:
    """A marker at `frame` (the current frame by default); one undo with the node when it is made."""
    frame = cmds.currentTime(q=True) if frame is None else float(frame)
    cmds.undoInfo(openChunk=True, chunkName="SyncBridge add marker")
    try:
        if not exists():
            _make_node()
        cmds.setKeyframe(NODE, attribute=ATTR, time=frame, value=0.0)
    finally:
        cmds.undoInfo(closeChunk=True)
    watch()
    return frame


def remove(frame: Optional[float] = None) -> Optional[float]:
    """Remove the marker nearest to `frame` within half a frame; returns its frame, or None."""
    frame = cmds.currentTime(q=True) if frame is None else float(frame)
    near = [f for f in frames() if abs(f - frame) <= NEAR]
    if not near:
        return None
    found = min(near, key=lambda f: abs(f - frame))
    cmds.cutKey("%s.%s" % (NODE, ATTR), time=(found, found), clear=True)
    return found


def select_node() -> str:
    """Select the node (made if needed, one undo): the Time Slider then shows its keys, to drag or delete."""
    if not exists():
        cmds.undoInfo(openChunk=True, chunkName="SyncBridge marker node")
        try:
            _make_node()
        finally:
            cmds.undoInfo(closeChunk=True)
    cmds.select(NODE, replace=True)
    watch()
    return NODE


# ---- bookmarks made from the keys -------------------------------------------------------------

def our_bookmarks() -> List[str]:
    try:
        nodes = cmds.ls(type="timeSliderBookmark") or []
    except RuntimeError:                          # the bookmark plug-in is not loaded
        return []
    return [n for n in nodes if cmds.attributeQuery(TAG_ATTR, node=n, exists=True)]


def _bookmark_frames() -> List[float]:
    return sorted(cmds.getAttr(b + ".timeRangeStart") for b in our_bookmarks())


def label(index: int, count: int) -> str:
    return core_markers.maya_marker_label(index, count)


def export() -> dict:
    """The markers with their AE comp times (core.markers.from_maya_frames): what a sync with AE will send.
    The Origin frame is the time sync's (timing.py, D-22)."""
    from . import key_markers, timing
    return core_markers.from_maya_frames(frames(), key_markers.scene_fps(), timing.origin())


def set_frames(new_frames: List[float]) -> None:
    """Replace the keys with these frames in one undo (what a sync from AE will call, after the user's OK:
    the markers are never replaced without asking)."""
    cmds.undoInfo(openChunk=True, chunkName="SyncBridge set markers")
    try:
        if not exists():
            _make_node()
        if frames():
            cmds.cutKey("%s.%s" % (NODE, ATTR), clear=True)
        for frame in new_frames:
            cmds.setKeyframe(NODE, attribute=ATTR, time=float(frame), value=0.0)
    finally:
        cmds.undoInfo(closeChunk=True)
    watch()


def update() -> List[float]:
    """Make the bookmarks match the keys (outside the undo queue: an undo of a key brings this back here)."""
    keys = frames()
    if keys == _bookmark_frames():
        return keys
    if keys and not cmds.pluginInfo(BOOKMARK_PLUGIN, q=True, loaded=True):
        cmds.loadPlugin(BOOKMARK_PLUGIN, quiet=True)
    with comp_guide._not_recorded_for_undo():
        # the bookmarks there are set again, nodes made or deleted only for a change of the count (a key dragged
        # along the Time Slider changes the frames many times)
        old = sorted(our_bookmarks(), key=lambda b: cmds.getAttr(b + ".timeRangeStart"))
        if len(old) > len(keys):
            cmds.delete(old[len(keys):])
        for index, frame in enumerate(keys, 1):
            if index <= len(old):
                bm = old[index - 1]
            else:
                bm = cmds.createNode("timeSliderBookmark", name="syncBridgeMarker%d" % index, skipSelect=True)
                cmds.addAttr(bm, longName=TAG_ATTR, attributeType="bool", defaultValue=True)
                cmds.setAttr(bm + ".color", *BOOKMARK_COLOR)
            cmds.setAttr(bm + ".name", label(index, len(keys)), type="string")
            cmds.setAttr(bm + ".timeRangeStart", frame)
            cmds.setAttr(bm + ".timeRangeStop", frame)
    return keys


def _overlay(has_keys: bool) -> None:
    """The view's top-left overlay (key_markers, D-18) shows 'マーカー 3/8' in cyan on a marker's frame; it is
    made with the first key and removed with the last one (unless AE markers are stored). Display only."""
    from . import key_markers
    if has_keys != bool(key_markers.overlays()):
        key_markers.restore_overlay()


def _run() -> None:
    state = _state()
    state["pending"] = False
    try:
        keys = update()
        _overlay(bool(keys))
        if _curve() != state.get("curve"):        # a first key, or every key deleted / undone
            watch()
        for fn in list(listeners):
            fn(keys)
    except Exception as exc:                      # never break the user's keying
        cmds.warning("SyncBridge markers: %s" % exc)


def _changed(*_args) -> None:
    """From the callbacks: the bookmarks are made once Maya is idle, a burst of changes once."""
    state = _state()
    if state["pending"]:
        return
    state["pending"] = True
    import maya.utils
    maya.utils.executeDeferred(_run)


def _curve() -> Optional[str]:
    if not exists():
        return None
    found = cmds.listConnections("%s.%s" % (NODE, ATTR), source=True, destination=False, type="animCurve")
    return found[0] if found else None


def unwatch() -> None:
    import maya.api.OpenMaya as om
    state = _state()
    for cid in state["callbacks"]:
        try:
            om.MMessage.removeCallback(cid)
        except RuntimeError:                      # its node is gone
            pass
    state["callbacks"] = []
    state["curve"] = None


def watch() -> None:
    """Follow the node's keys (again: the curve is a new node after every key was deleted and undone)."""
    import maya.api.OpenMaya as om
    unwatch()
    state = _state()
    if exists():
        sel = om.MSelectionList()
        sel.add(NODE)
        state["callbacks"].append(om.MNodeMessage.addAttributeChangedCallback(sel.getDependNode(0), _changed))
        state["callbacks"].append(om.MNodeMessage.addNodePreRemovalCallback(sel.getDependNode(0), _changed))
        curve = _curve()
        if curve:
            sel = om.MSelectionList()
            sel.add(curve)
            state["callbacks"].append(om.MNodeMessage.addNodeDirtyCallback(sel.getDependNode(0), _changed))
        state["curve"] = curve
    _changed()                                    # the bookmarks of a scene just opened, or none left
