"""Clean a scene for delivery: remove what SyncBridge made in it (D-47, the user 2026-10-29).

    found = cleanup.inventory()             what is in the scene (for the confirmation)
    result = cleanup.run(keep_cameras=True)

Removed:
  * the viewer (its window and the SB_VIEWER_* nodes), the comp guide and the key marker overlay:
    display only, never saved and not in the undo history (as when the panel clears them)
  * the key markers (syncBridgeKeyMarkers and our Time Slider Bookmarks)
  * the layer map (syncBridgeLayerMappings) and the Origin frame (syncBridgeTiming)
The dedicated cameras (D-29) hold the 2D motion SyncBridge keyed, so the user chooses each time:
  keep   -> plain cameras: the syncBridgeLayer attribute goes and the transform is unlocked; the keys and
            the connections from the original camera stay, so renders through them do not change
  delete -> deleted with their keys
Kept: the Scene Time Warp (the deliverable), the user's own nodes and bookmarks, the optionVars
(preferences, not in the scene). The scene nodes come back with one undo; a JSON backup of the
stored records is written first (development rule 2).
"""
from __future__ import annotations

import datetime
import json
import os
from typing import List, Optional

from maya import cmds

from . import comp_guide, key_markers, layer_camera, layer_mapping, timing, viewer_camera

PREFIXES = ("syncBridge", "SB_")


def dedicated_cameras() -> List[str]:
    """Transforms of the dedicated cameras, also those the layer map no longer knows."""
    found = cmds.ls("*." + layer_camera.MARK_ATTR, objectsOnly=True, long=True, recursive=True) or []
    return [n for n in found if cmds.nodeType(n) == "transform"]


def _key_count(transform: str) -> int:
    nodes = [transform] + (cmds.listRelatives(transform, shapes=True, fullPath=True) or [])
    curves = set()
    for node in nodes:
        curves.update(cmds.listConnections(node, type="animCurve", source=True, destination=False) or [])
    return sum(cmds.keyframe(c, q=True, keyframeCount=True) or 0 for c in curves)


def _data_nodes() -> List[str]:
    return [n for n in (layer_mapping.DATA_NODE, key_markers.DATA_NODE, timing.NODE) if cmds.objExists(n)]


def _display_nodes() -> List[str]:
    return viewer_camera._nodes() + comp_guide.existing() + key_markers.overlays()


def inventory() -> dict:
    """{cameras: [{name, keys}], layers, links, markers, bookmarks, origin, display, any}."""
    store = layer_mapping.store()
    markers = key_markers.stored() or {}
    out = {
        "cameras": [{"name": c.split("|")[-1], "path": c, "keys": _key_count(c)} for c in dedicated_cameras()],
        "layers": len(store.get("maya_layers") or []) if cmds.objExists(layer_mapping.DATA_NODE) else 0,
        "links": len(store.get("mappings") or []) if cmds.objExists(layer_mapping.DATA_NODE) else 0,
        "layer_map": cmds.objExists(layer_mapping.DATA_NODE),
        "markers": len(markers.get("markers") or []),
        "bookmarks": len(key_markers.our_bookmarks()),
        "origin": timing.origin() if timing.is_set() else None,
        "display": len(_display_nodes()),
    }
    out["any"] = bool(out["cameras"] or _data_nodes() or out["bookmarks"] or out["display"])
    return out


def _backup(found: dict) -> str:
    from .exchange import backup_dir
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = os.path.join(backup_dir(), "cleanup_%s.json" % stamp)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"syncbridge": "delivery cleanup backup", "scene": cmds.file(q=True, sn=True),
                   "layer_map": layer_mapping.store() if found["layer_map"] else None,
                   "key_markers": key_markers.stored(), "origin_frame": found["origin"],
                   "cameras": found["cameras"]}, f, indent=2, ensure_ascii=False)
    return path


def close_tools() -> bool:
    """Close the viewer and the layer map (they would make the nodes again, and the viewer camera is a child
    of a dedicated camera) and stop the live sync. Returns whether the live sync was stopped.

    Closing the viewer deletes its model panel, and Maya then puts selectionMaskResetAll on the undo queue
    a moment later (H-MY-46, Maya 2023 / 2024 GUI): the panel calls this first and run() after Maya's
    deferred commands, so that the first undo restores the scene."""
    from . import layer_map_window, live_sync, service, viewer_window
    for module in (viewer_window, layer_map_window):
        window = getattr(module, "_window", None)
        if window is None:
            continue
        try:
            window.close()
        except RuntimeError:       # already deleted by Qt
            pass
    if live_sync.state.get("enabled") and service.is_connected():
        service.set_live_sync(False)
        return True
    return False


def _plain_camera(transform: str) -> None:
    cmds.deleteAttr("%s.%s" % (transform, layer_camera.MARK_ATTR))
    for attr in layer_camera.PLACE_ATTRS:
        cmds.setAttr("%s.%s" % (transform, attr), lock=False)


def leftovers(kept: Optional[List[str]] = None) -> List[str]:
    """Nodes still named like ours (the user's own may be among them), without the cameras kept."""
    out = []
    for prefix in PREFIXES:
        out += cmds.ls(prefix + "*", long=True, recursive=True) or []
    kept = kept or []
    curves = set()                         # the kept cameras' keys
    for camera in kept:
        for node in [camera] + (cmds.listRelatives(camera, shapes=True, fullPath=True) or []):
            curves.update(cmds.ls(cmds.listConnections(node, type="animCurve", source=True, destination=False)
                                  or [], long=True))
    return sorted(n for n in set(out) - curves if not any(n == k or n.startswith(k + "|") for k in kept))


def run(keep_cameras: bool = True, backup: bool = True, live_stopped: bool = False) -> dict:
    """Remove SyncBridge's nodes (see the module). Returns what was done. live_stopped: close_tools()
    was called before and stopped the live sync."""
    found = inventory()
    path = _backup(found) if backup and found["any"] else None
    live_stopped = close_tools() or live_stopped
    viewer_camera.remove()
    comp_guide.clear()
    key_markers.remove_overlay()
    cameras = dedicated_cameras()
    cmds.undoInfo(openChunk=True, chunkName="SyncBridge delivery cleanup")
    try:
        if keep_cameras:
            for camera in cameras:
                _plain_camera(camera)
        elif cameras:
            cmds.delete(cameras)
        nodes = key_markers.our_bookmarks() + _data_nodes()
        if nodes:
            cmds.delete(nodes)
    finally:
        cmds.undoInfo(closeChunk=True)
    return {"cameras": [c["name"] for c in found["cameras"]], "cameras_kept": bool(keep_cameras),
            "layer_map": found["layer_map"], "markers": found["bookmarks"], "origin": found["origin"],
            "display": found["display"], "live_stopped": live_stopped, "backup": path,
            "leftovers": [n.split("|")[-1] for n in leftovers(cameras if keep_cameras else None)]}


def summary_lines(found: dict) -> List[str]:
    """What run() removes, for the confirmation (Japanese, for the user)."""
    lines = []
    if found["layer_map"]:
        lines.append(u"レイヤーマップ（Maya レイヤー %d、接続 %d）" % (found["layers"], found["links"]))
    if found["bookmarks"] or found["markers"]:
        lines.append(u"AE のキーのマーカー（ブックマーク %d）" % found["bookmarks"])
    if found["origin"] is not None:
        lines.append(u"Origin frame の記録（%g）" % found["origin"])
    if found["display"]:
        lines.append(u"ビューアー・解像度の枠などの表示用のノード（%d）" % found["display"])
    return lines


def result_text(result: dict) -> str:
    parts = []
    if result["cameras"]:
        parts.append(u"専用カメラ %d 台を%s" % (len(result["cameras"]),
                                              u"普通のカメラにしました" if result["cameras_kept"] else u"消しました"))
    if result["layer_map"]:
        parts.append(u"レイヤーマップを消しました")
    if result["markers"]:
        parts.append(u"キーのマーカー %d 個を消しました" % result["markers"])
    if result["origin"] is not None:
        parts.append(u"Origin frame の記録を消しました")
    if result["display"]:
        parts.append(u"表示用のノードを消しました")
    if result["live_stopped"]:
        parts.append(u"リアルタイム同期をオフにしました")
    text = u"、".join(parts) + u"。" if parts else u"SyncBridge のノードはありませんでした。"
    if parts:
        text += u"取り消し 1 回で戻せます（ビューアー・枠は開き直してください）。"
    if result["leftovers"]:
        text += u"\n名前が SB_ / syncBridge で始まるノードが残っています（ご自分で作ったものかもしれません）: %s" % \
            u", ".join(result["leftovers"][:10])
    if result["backup"]:
        text += u"\nバックアップ: %s" % result["backup"]
    return text
