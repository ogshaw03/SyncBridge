"""Locate the Maya *Scene* Time Warp (not a generic `timeWarp` deformer-style node).

Observed in the first probe (Maya 2024, 2026-10-16; docs/PHASE0_RESEARCH.md H-MY-1/2):
  * The Scene Time Warp is an animCurveTT named `timewarp`, connected
    `timewarp.apply -> time1.timewarpIn_Raw` (note: from `.apply`, not `.output`).
  * `time1.enableTimewarp` (bool) exists. `time1` also has `timewarpIn`
    (compound: _Raw, _Hidden, _Inmap, _Outmap) and `unwarpedTime`.
  * Created / deleted / selected by the MEL procedure `sceneTimeWarp "add"`,
    `"delete"`, `"select"` (runtime commands AddTimeWarp, DeleteTimeWarp,
    SelectTimeWarp). Not called from here yet (D-7).
Not yet confirmed on Maya 2023. Discovery still searches connections instead of
hard-coding names.
"""
from __future__ import annotations

from maya import cmds

TIME_NODE = "time1"
ENABLE_ATTR = "enableTimewarp"


class SceneTimeWarpNotFound(RuntimeError):
    pass


def find_curve():
    """Return (curve node, destination plug on time1) or raise SceneTimeWarpNotFound."""
    conns = cmds.listConnections(TIME_NODE, source=True, destination=False,
                                 plugs=True, connections=True) or []
    # listConnections -connections returns [dst_plug, src_plug, dst_plug, src_plug, ...]
    for dst, src in zip(conns[0::2], conns[1::2]):
        node = src.split(".")[0]
        if "timewarp" in dst.split(".")[-1].lower() and cmds.nodeType(node) == "animCurveTT":
            return node, dst
    raise SceneTimeWarpNotFound(
        "No Scene Time Warp curve connected to %s. Create one from the Maya UI "
        "first (Phase 0 does not create it)." % TIME_NODE)


def is_enabled():
    """True/False, or None when the enable attribute does not exist (H-MY-2 false)."""
    if not cmds.attributeQuery(ENABLE_ATTR, node=TIME_NODE, exists=True):
        return None
    return bool(cmds.getAttr("%s.%s" % (TIME_NODE, ENABLE_ATTR)))
