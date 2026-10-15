"""Locate the Maya *Scene* Time Warp (not a generic `timeWarp` deformer-style node).

Structure assumed until confirmed by probe.py on Maya 2023 (H-MY-1/2 in
docs/PHASE0_RESEARCH.md):
  * The Scene Time Warp created from the Maya UI is an animCurveTT whose
    output is connected to an input attribute of the `time1` node whose name
    contains "timewarp" (case-insensitive).
  * `time1.enableTimewarp` (bool) switches the warp on and off.

Discovery is done by connection search instead of hard-coded names so the
probe result can confirm or correct the assumption.
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
