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
VAR_VIEW_OVERSCAN = "syncBridgePixelMapViewOverscan"   # 1: AE footage shows the overscan margin (default 0)


def store() -> dict:
    """The scene's store: {"maya_layers", "mappings"} (D-28; schema 1 scenes are moved on read)."""
    if not cmds.objExists(DATA_NODE) or not cmds.attributeQuery(DATA_ATTR, node=DATA_NODE, exists=True):
        return core.empty_store()
    text = cmds.getAttr("%s.%s" % (DATA_NODE, DATA_ATTR)) or ""
    return core.load_store(json.loads(text)) if text else core.empty_store()


def save_store(data: dict) -> None:
    if not cmds.objExists(DATA_NODE):
        cmds.createNode("network", name=DATA_NODE, skipSelect=True)
    if not cmds.attributeQuery(DATA_ATTR, node=DATA_NODE, exists=True):
        cmds.addAttr(DATA_NODE, longName=DATA_ATTR, dataType="string")
    cmds.setAttr("%s.%s" % (DATA_NODE, DATA_ATTR), json.dumps(core.dump_store(data), ensure_ascii=False),
                 type="string")


def stored() -> List[dict]:
    """The links (AE layer -> Maya layer)."""
    return store()["mappings"]


def save(mappings: List[dict]) -> None:
    """Replace the links, keeping the Maya layers."""
    data = store()
    data["mappings"] = list(mappings)
    save_store(core.load_store(core.dump_store(data)))       # links without a Maya layer get one


def object_entries(nodes: List[str]) -> List[dict]:
    """[{uuid, name}] for Maya nodes (the objects a Maya layer shows)."""
    out = []
    for node in nodes:
        long_name = (cmds.ls(node, long=True) or [node])[0]
        out.append({"uuid": uuid_of(long_name), "name": long_name})
    return out


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
    view_overscan = var(VAR_VIEW_OVERSCAN)
    return {"camera": node_by_uuid(var(VAR_CAMERA)), "bg": node_by_uuid(var(VAR_BG)),
            "method": var(VAR_METHOD) or "pan_zoom", "mode": var(VAR_MODE) or "relative",
            # the user playblasts without the overscan margin (2026-10-25): footage framed like a render
            "view_overscan": False if view_overscan is None else bool(view_overscan)}


def set_defaults(camera: Optional[str] = None, bg: Optional[str] = None, method: Optional[str] = None,
                 mode: Optional[str] = None, view_overscan: Optional[bool] = None) -> None:
    if camera:
        cmds.optionVar(stringValue=(VAR_CAMERA, uuid_of(camera)))
    if bg:
        cmds.optionVar(stringValue=(VAR_BG, uuid_of(bg)))
    if method:
        cmds.optionVar(stringValue=(VAR_METHOD, method))
    if mode:
        cmds.optionVar(stringValue=(VAR_MODE, mode))
    if view_overscan is not None:
        cmds.optionVar(intValue=(VAR_VIEW_OVERSCAN, int(bool(view_overscan))))


def reset_reference(mapping_id: str) -> None:
    """Relative mode: the next send records a new reference (undoable)."""
    save([core.without_reference(m) if m["id"] == mapping_id else m for m in stored()])


def change_method(mapping_id: str, method: str) -> dict:
    """Use another method for one record (undoable); relative records take a new reference next time."""
    mappings = stored()
    changed = None
    out = []
    for m in mappings:
        if m["id"] == mapping_id:
            m = changed = core.with_method(m, method)
        out.append(m)
    if changed is None:
        raise ValueError(u"対応付けが見つかりません。")
    save(out)
    return changed


def remove(mapping_id: str) -> int:
    """Delete one record (undoable). Returns how many records are left."""
    mappings = core.remove(stored(), mapping_id)
    save(mappings)
    return len(mappings)


# -- layer map (D-28): every change is one undo chunk -------------------------------------------------
class _Chunk(object):
    def __init__(self, name):
        self.name = name

    def __enter__(self):
        cmds.undoInfo(openChunk=True, chunkName=self.name)

    def __exit__(self, *exc):
        cmds.undoInfo(closeChunk=True)
        return False


def _edit(name, fn):
    """fn(store) changes the store; it is saved in one undo chunk. Returns what fn returns."""
    with _Chunk(name):
        data = store()
        result = fn(data)
        save_store(data)
    return result


def _mapping(data: dict, mapping_id: str) -> dict:
    for m in data["mappings"]:
        if m["id"] == mapping_id:
            return m
    raise ValueError(u"接続が見つかりません。")


def _layer(data: dict, layer_id: str) -> dict:
    layer = core.maya_layer(data, layer_id)
    if layer is None:
        raise ValueError(u"Maya レイヤーが見つかりません。")
    return layer


def selected_camera() -> Optional[str]:
    """The camera shape of the selection (a camera transform or shape)."""
    for node in cmds.ls(selection=True, long=True) or []:
        if cmds.nodeType(node) == "camera":
            return node
        shapes = cmds.listRelatives(node, shapes=True, type="camera", fullPath=True) or []
        if shapes:
            return shapes[0]
    return None


def selected_objects() -> List[str]:
    """Selected DAG objects (transforms of shapes are kept as transforms), without cameras."""
    out = []
    for node in cmds.ls(selection=True, long=True, dag=True, objectsOnly=True) or []:
        if cmds.nodeType(node) == "camera" or (cmds.listRelatives(node, shapes=True, type="camera") or []):
            continue
        if cmds.objectType(node, isAType="shape"):
            node = (cmds.listRelatives(node, parent=True, fullPath=True) or [node])[0]
        if node not in out:
            out.append(node)
    return out


def selected_mesh() -> Optional[str]:
    for node in selected_objects():
        if cmds.listRelatives(node, shapes=True, type="mesh") or cmds.nodeType(node) == "mesh":
            return node
    return None


def add_layer(name: Optional[str] = None) -> dict:
    """A new Maya layer; it uses the selected camera and objects when there are any."""
    camera = selected_camera()
    objects = object_entries(selected_objects())

    def fn(data):
        layer = core.new_maya_layer(name or (core.short_name(camera).replace("Shape", "") if camera else
                                             u"Layer %d" % (len(data["maya_layers"]) + 1)),
                                    uuid_of(camera) if camera else None, camera, objects)
        data["maya_layers"].append(layer)
        return layer
    return _edit("SyncBridge add layer", fn)


def rename_layer(layer_id: str, name: str) -> None:
    _edit("SyncBridge rename layer", lambda data: _layer(data, layer_id).update(name=name))


def set_camera_from_selection(layer_id: str) -> dict:
    camera = selected_camera()
    if not camera:
        raise ValueError(u"カメラを選んでから押してください。")
    return _edit("SyncBridge layer camera",
                 lambda data: core.set_layer_camera(data, layer_id, uuid_of(camera), camera))


def add_selected_objects(layer_id: str) -> int:
    entries = object_entries(selected_objects())
    if not entries:
        raise ValueError(u"オブジェクトを選んでから押してください。")

    def fn(data):
        layer = _layer(data, layer_id)
        known = set(o.get("uuid") for o in layer.get("objects") or [])
        added = [e for e in entries if e["uuid"] not in known]
        layer["objects"] = list(layer.get("objects") or []) + added
        return len(added)
    return _edit("SyncBridge layer objects", fn)


def remove_objects(layer_id: str, uuids: List[str]) -> None:
    def fn(data):
        layer = _layer(data, layer_id)
        layer["objects"] = [o for o in layer.get("objects") or [] if o.get("uuid") not in uuids]
    _edit("SyncBridge layer objects", fn)


def select_layer(layer_id: str) -> List[str]:
    """Select the layer's camera and objects in Maya. Returns the names of those no longer in the scene."""
    layer = _layer(store(), layer_id)
    found, missing = [], []
    entries = ([{"uuid": layer.get("camera_uuid"), "name": layer.get("camera")}] if layer.get("camera_uuid")
               else []) + list(layer.get("objects") or [])
    for entry in entries:
        node = node_by_uuid(entry.get("uuid"))
        (found if node else missing).append(node or core.short_name(entry.get("name")))
    if found:
        cmds.select(found, replace=True)
    else:
        cmds.select(clear=True)
    return missing


def remove_layer(layer_id: str) -> int:
    return _edit("SyncBridge remove layer", lambda data: core.remove_maya_layer(data, layer_id))


def connect(ae: dict, layer_id: str) -> dict:
    """Link an AE layer (core.layer_mapping.ae_from_layers_info) to a Maya layer with the panel's method
    and mode; absolute mode uses the panel's BG."""
    chosen = defaults()

    def fn(data):
        mode = chosen["mode"]
        bg = {"uuid": uuid_of(chosen["bg"]), "name": chosen["bg"]} if mode == "absolute" and chosen["bg"] else None
        if mode == "absolute" and bg is None:
            mode = "relative"
        return dict(core.connect(data, ae, layer_id, chosen["method"], mode, bg))
    return _edit("SyncBridge connect", fn)


def disconnect(mapping_id: str) -> None:
    _edit("SyncBridge disconnect", lambda data: core.disconnect(data, mapping_id))


def change_mode(mapping_id: str, mode: str) -> dict:
    """Relative / absolute for one link; absolute takes the selected mesh as its BG (or the recorded one)."""
    mesh = selected_mesh()
    bg = {"uuid": uuid_of(mesh), "name": mesh} if mesh and mode == "absolute" else None

    def fn(data):
        m = _mapping(data, mapping_id)
        changed = core.with_mode(m, mode, bg)
        m.clear()
        m.update(changed)
        return dict(m)
    return _edit("SyncBridge mode", fn)
