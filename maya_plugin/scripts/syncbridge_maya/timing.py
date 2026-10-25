"""One Origin frame for the whole tool (D-38): the Maya frame of AE comp time 0, kept in the scene.

    timing.origin()             the scene's Origin frame (the playback start when it was never set)
    timing.set_origin(1001)     keep it in the scene (not an undo step: the panels and the hub follow it)
    timing.playback_range()     the tool's range: Maya's playback range (the user's choice, 2026-10-25)

The Maya panel, the AE panel (through the hub's timing.state), the time slider sync, the transfers, the
key markers, the scene settings and the layer map all use this one value.
"""
from __future__ import annotations

from typing import Tuple

from maya import cmds

NODE = "syncBridgeTiming"
ATTR = "originFrame"


def origin() -> float:
    if cmds.objExists(NODE) and cmds.attributeQuery(ATTR, node=NODE, exists=True):
        return float(cmds.getAttr("%s.%s" % (NODE, ATTR)))
    return float(cmds.playbackOptions(q=True, minTime=True))


def is_set() -> bool:
    return cmds.objExists(NODE) and cmds.attributeQuery(ATTR, node=NODE, exists=True)


def set_origin(value: float) -> bool:
    """Keep the Origin frame in the scene; True when it changed. Not recorded for undo: an undo would
    leave the panels and the hub on the other value."""
    value = float(value)
    if is_set() and abs(origin() - value) < 1e-9:
        return False
    was_on = cmds.undoInfo(q=True, state=True)
    cmds.undoInfo(stateWithoutFlush=False)
    try:
        if not cmds.objExists(NODE):
            cmds.createNode("network", name=NODE, skipSelect=True)
        if not cmds.attributeQuery(ATTR, node=NODE, exists=True):
            cmds.addAttr(NODE, longName=ATTR, attributeType="double")
        cmds.setAttr("%s.%s" % (NODE, ATTR), value)
    finally:
        cmds.undoInfo(stateWithoutFlush=was_on)
    return True


def playback_range() -> Tuple[float, float]:
    return float(cmds.playbackOptions(q=True, minTime=True)), float(cmds.playbackOptions(q=True, maxTime=True))
