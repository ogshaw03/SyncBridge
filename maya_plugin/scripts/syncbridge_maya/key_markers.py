"""AE Time Remap key timings as markers in Maya (D-18).

    apply(export_envelope, options)   from AE (markers.apply.request)
    clear()                            the panel's "マーカーを消す"
    restore_overlay()                  the panel on open, the plug-in after a scene is opened

What is stored in the scene (undoable in one step, saved, readable without AE or SyncBridge):
  * network node syncBridgeKeyMarkers.markers = JSON of core.markers.from_ae_export()
  * one Time Slider Bookmark per key (Autodesk's timeSliderBookmark plug-in, Maya 2020+),
    tagged with the attribute syncBridgeMarker so a new transfer replaces only ours
What is only shown (not saved, not in the undo history, like the comp guide of D-16):
  * the viewport overlay node syncBridgeKeyMarker (plug-ins/syncbridge_guide.py), which reads
    the network node by name on every draw and shows "AE キー 3/8  素材 36f" while the
    current frame is on a key

Checked with mayapy 2023 / 2024: timeSliderBookmark needs its plug-in loaded (not loaded in
mayapy), the saved file then has `requires "timeSliderBookmark"` (an Autodesk plug-in that
comes with Maya); Japanese names and the JSON survive save and reopen. The overlay drawing
is H-MY-24 (not yet run in the GUI).
"""
from __future__ import annotations

import json
from typing import List, Optional

from maya import cmds

from syncbridge.core import markers as core
from syncbridge.core.timebase import FrameRate

from . import comp_guide

DATA_NODE = "syncBridgeKeyMarkers"
DATA_ATTR = "markers"
TAG_ATTR = "syncBridgeMarker"            # on our bookmarks
OVERLAY_TYPE = "syncBridgeKeyMarker"
OVERLAY_NAME = "syncBridgeKeyMarker"
BOOKMARK_PLUGIN = "timeSliderBookmark"
BOOKMARK_COLOR = (1.0, 0.55, 0.1)        # same orange as the comp guide


def scene_fps() -> FrameRate:
    return FrameRate.from_maya_unit(cmds.currentUnit(q=True, time=True))


# ---- data stored in the scene -------------------------------------------------------------

def stored() -> Optional[dict]:
    """The markers stored in this scene, or None."""
    if not cmds.objExists(DATA_NODE) or not cmds.attributeQuery(DATA_ATTR, node=DATA_NODE, exists=True):
        return None
    try:
        return json.loads(cmds.getAttr("%s.%s" % (DATA_NODE, DATA_ATTR)) or "null")
    except ValueError:
        return None


def our_bookmarks() -> List[str]:
    try:
        nodes = cmds.ls(type="timeSliderBookmark") or []
    except RuntimeError:
        return []
    return [n for n in nodes if cmds.attributeQuery(TAG_ATTR, node=n, exists=True)]


def _ensure_bookmark_plugin() -> None:
    if not cmds.pluginInfo(BOOKMARK_PLUGIN, q=True, loaded=True):
        cmds.loadPlugin(BOOKMARK_PLUGIN, quiet=True)


def _write(result: dict) -> List[str]:
    """Data node and bookmarks (inside the caller's undo chunk)."""
    node = cmds.createNode("network", name=DATA_NODE, skipSelect=True)
    cmds.addAttr(node, longName=DATA_ATTR, dataType="string")
    cmds.setAttr("%s.%s" % (node, DATA_ATTR), json.dumps(result, ensure_ascii=False), type="string")
    bookmarks = []
    for marker in result["markers"]:
        bm = cmds.createNode("timeSliderBookmark", name="syncBridgeKey%d" % marker["index"], skipSelect=True)
        cmds.addAttr(bm, longName=TAG_ATTR, attributeType="bool", defaultValue=True)
        cmds.setAttr(bm + ".name", marker["label"], type="string")
        cmds.setAttr(bm + ".timeRangeStart", marker["frame"])
        cmds.setAttr(bm + ".timeRangeStop", marker["frame"])
        cmds.setAttr(bm + ".color", *BOOKMARK_COLOR)
        bookmarks.append(bm)
    return bookmarks


def _delete_stored() -> int:
    nodes = our_bookmarks()
    if cmds.objExists(DATA_NODE):
        nodes.append(DATA_NODE)
    if nodes:
        cmds.delete(nodes)
    return len(nodes)


def apply(export_env: dict, options: Optional[dict] = None) -> dict:
    """Replace the SyncBridge markers of this scene with the keys of an AE export."""
    result = core.from_ae_export(export_env["data"], scene_fps(), options)
    _ensure_bookmark_plugin()
    cmds.undoInfo(openChunk=True, chunkName="SyncBridge key markers")
    try:
        _delete_stored()
        bookmarks = _write(result)
    finally:
        cmds.undoInfo(closeChunk=True)
    overlay = restore_overlay()
    frames = [m["frame"] for m in result["markers"]]
    return {"status": "applied", "count": len(frames), "first": _frame_text(min(frames)),
            "last": _frame_text(max(frames)), "bookmarks": len(bookmarks), "overlay": overlay,
            "comp": result["comp"], "layer": result["layer"]}


def clear() -> int:
    """Delete the stored markers and bookmarks (one undo) and the overlay. Returns the count."""
    count = len((stored() or {}).get("markers") or [])
    remove_overlay()
    if cmds.objExists(DATA_NODE) or our_bookmarks():
        cmds.undoInfo(openChunk=True, chunkName="SyncBridge clear key markers")
        try:
            _delete_stored()
        finally:
            cmds.undoInfo(closeChunk=True)
    return count


def _frame_text(value: float) -> str:
    return core._frame_text(value)


# ---- viewport overlay (display only) ------------------------------------------------------

def overlays() -> List[str]:
    try:
        return cmds.ls(type=OVERLAY_TYPE, long=True) or []
    except RuntimeError:
        return []


def remove_overlay() -> int:
    shapes = overlays()
    if not shapes:
        return 0
    with comp_guide._not_recorded_for_undo():
        # The overlay is not connected to the network node: with a connection, `delete` also
        # removed the stored markers (an upstream node used by nothing else; mayapy 2023 / 2024),
        # and a new transfer left the overlay connected to nothing.
        return comp_guide._delete(shapes)


def restore_overlay() -> bool:
    """Show the overlay for the markers stored in this scene. Returns whether it is shown."""
    if stored() is None:
        remove_overlay()
        return False
    comp_guide.ensure_plugin()
    if overlays():
        return True
    with comp_guide._not_recorded_for_undo():
        transform = cmds.createNode("transform", name=OVERLAY_NAME, skipSelect=True)
        transform = cmds.ls(transform, long=True)[0]
        try:
            shape = cmds.createNode(OVERLAY_TYPE, name=OVERLAY_NAME + "Shape", parent=transform, skipSelect=True)
            shape = cmds.ls(shape, long=True)[0]
            if cmds.attributeQuery("hiddenInOutliner", node=transform, exists=True):
                cmds.setAttr(transform + ".hiddenInOutliner", True)
            for attr in ("translate", "rotate", "scale"):
                cmds.setAttr("%s.%s" % (transform, attr), lock=True)
            for node in (transform, shape):
                comp_guide._do_not_write(node)
        except Exception:
            if cmds.objExists(transform):
                cmds.delete(transform)
            raise
    return True


def take_out_for_save() -> bool:
    """Called by the plug-in before a save (the overlay would add `requires syncbridge_guide.py`)."""
    return remove_overlay() > 0


def put_back_after_save(was_shown: bool) -> None:
    if was_shown:
        restore_overlay()
