"""Virtual Layer Mapping, Maya side (D-24): the records live in the scene, nodes are found by UUID.

    stored() / save(mappings)                     the scene's syncBridgeLayerMappings node (JSON)
    defaults() / set_defaults(...)                 camera / BG / method chosen in the SyncBridge panel
    node_by_uuid(uuid) / uuid_of(node)

Records: syncbridge.core.layer_mapping. Saving is a plain setAttr, so it is undone together with the
camera change when both are done in one undo chunk (pixel_mapping.apply_from_ae).
"""
from __future__ import annotations

import json
from typing import List, Optional

from maya import cmds

from syncbridge.core import layer_mapping as core

DATA_NODE = "syncBridgeLayerMappings"
DATA_ATTR = "mappings"
VAR_CAMERA = "syncBridgePixelMapCamera"      # optionVar: camera shape UUID
VAR_BG = "syncBridgePixelMapBG"              # optionVar: BG mesh UUID
VAR_METHOD = "syncBridgePixelMapMethod"
VAR_MODE = "syncBridgePixelMapMode"          # relative (default, D-25) | absolute


def stored() -> List[dict]:
    if not cmds.objExists(DATA_NODE) or not cmds.attributeQuery(DATA_ATTR, node=DATA_NODE, exists=True):
        return []
    text = cmds.getAttr("%s.%s" % (DATA_NODE, DATA_ATTR)) or ""
    return core.load(json.loads(text)) if text else []


def save(mappings: List[dict]) -> None:
    if not cmds.objExists(DATA_NODE):
        cmds.createNode("network", name=DATA_NODE, skipSelect=True)
    if not cmds.attributeQuery(DATA_ATTR, node=DATA_NODE, exists=True):
        cmds.addAttr(DATA_NODE, longName=DATA_ATTR, dataType="string")
    cmds.setAttr("%s.%s" % (DATA_NODE, DATA_ATTR), json.dumps(core.dump(mappings), ensure_ascii=False),
                 type="string")


def uuid_of(node: str) -> str:
    found = cmds.ls(node, uuid=True) or []
    if not found:
        raise ValueError(u"%s が見つかりません。" % node)
    return found[0]


def node_by_uuid(node_uuid: str) -> Optional[str]:
    """Full path of the node with this UUID (None when it is not in the scene)."""
    if not node_uuid:
        return None
    found = cmds.ls(node_uuid, long=True) or []
    return found[0] if found else None


def cameras() -> List[str]:
    """Camera shapes the user can pick (Maya's startup cameras last)."""
    shapes = cmds.ls(type="camera", long=True) or []
    startup = [s for s in shapes if cmds.camera(s, q=True, startupCamera=True)]
    return [s for s in shapes if s not in startup] + startup


def meshes() -> List[str]:
    """Transforms of meshes (BG candidates)."""
    out = []
    for shape in cmds.ls(type="mesh", long=True, noIntermediate=True) or []:
        parent = (cmds.listRelatives(shape, parent=True, fullPath=True) or [None])[0]
        if parent and parent not in out:
            out.append(parent)
    return out


def defaults() -> dict:
    """{camera, bg, method, mode} chosen in the panel (paths; None when not chosen or gone).
    First time: relative mode with 2D Pan/Zoom (works with 3D BGs and camera work, D-25)."""
    def var(name):
        return cmds.optionVar(q=name) if cmds.optionVar(exists=name) else None
    return {"camera": node_by_uuid(var(VAR_CAMERA)), "bg": node_by_uuid(var(VAR_BG)),
            "method": var(VAR_METHOD) or "pan_zoom", "mode": var(VAR_MODE) or "relative"}


def set_defaults(camera: Optional[str] = None, bg: Optional[str] = None, method: Optional[str] = None,
                 mode: Optional[str] = None) -> None:
    if camera:
        cmds.optionVar(stringValue=(VAR_CAMERA, uuid_of(camera)))
    if bg:
        cmds.optionVar(stringValue=(VAR_BG, uuid_of(bg)))
    if method:
        cmds.optionVar(stringValue=(VAR_METHOD, method))
    if mode:
        cmds.optionVar(stringValue=(VAR_MODE, mode))


def reset_reference(mapping_id: str) -> None:
    """Relative mode: the next send records a new reference (undoable)."""
    save([core.without_reference(m) if m["id"] == mapping_id else m for m in stored()])


def remove(mapping_id: str) -> int:
    """Delete one record (undoable). Returns how many records are left."""
    mappings = core.remove(stored(), mapping_id)
    save(mappings)
    return len(mappings)
