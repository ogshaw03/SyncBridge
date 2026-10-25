"""Virtual Layer Mapping (Pixel Mapping Phase 2, docs/PIXEL_MAPPING.md, D-24, D-28).

The store kept in the Maya scene (syncbridge_maya.layer_mapping), so it travels with the scene:

    {"schema_version": 2,
     "maya_layers": [ Maya layer, ... ],      SyncBridge's own layers (not Maya display / render layers)
     "mappings":    [ link, ... ]}            an AE layer connected to a Maya layer (the node editor's wire)

A Maya layer (D-28) holds the camera it uses and the objects it shows (recorded and selectable; showing
only them is a later phase):

    {"id": "ml-1a2b...", "name": "BG", "camera_uuid": "...", "camera": "|SHOT_CAM|SHOT_CAMShape",
     "layer_camera_uuid": "...", "layer_camera": "|SHOT_CAM|SB_BG_CAM|SB_BG_CAMShape",
     "objects": [{"uuid": "...", "name": "|town|building01"}, ...]}

`camera` is the camera the layer uses (the original, it has the camera work); `layer_camera` is the
layer's dedicated camera, a child of it (D-29), which its links move. Layers moved from schema 1 have
no dedicated camera: their links move the original camera (as before).

A link (the former "virtual layer" record of D-24; `maya_layer` added in schema 2, its camera fields are
kept in step with the Maya layer):

    {
      "id": "vl-3f2a...",                 unique, never reused
      "name": "BG Slide",
      "ae": {"comp_id": 12, "comp": "c010", "layer_id": 345, "layer": "BG", "source": "bg_c010.psd",
             "source_width": 6000, "source_height": 4000},
      "maya": {"camera_uuid": "...", "camera": "|BG_CAM|BG_CAMShape", "bg_uuid": "...", "bg": "|bgPlane"},
      "enabled": true,
      "direction": "ae2maya",             only direction so far
      "properties": ["pan"],              what is synced
      "method": "film_offset"             film_offset | film_translate | pan_zoom (core.pixel_mapping)
      "mode": "relative",                 relative (D-25, no BG geometry) | absolute (BG plane, D-24)
      "reference": {"matrix": [[...]], "camera": {attr: value}, "comp_time": 0.5}   relative mode only;
                                          None until the first send records it
      "maya_layer": "ml-1a2b..."          the Maya layer it is connected to (schema 2)
    }

A store of schema 1 (links only) is moved to schema 2 on load: one Maya layer per camera.

AE layers are found by comp id + layer id (H-AE-26: Layer.id is persistent, AE 22+); when the id is
unknown, by comp name + layer name. Maya nodes are found by UUID (survives renaming and namespace
changes), the stored name is only shown to the user. Pure functions, standard library only.
"""
from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from .pixel_mapping import METHODS

DIRECTIONS = ("ae2maya",)
PROPERTIES = ("pan",)
MODES = ("relative", "absolute")
MODE_LABELS = {"relative": u"相対", "absolute": u"絶対"}
SCHEMA_VERSION = 2


# -- Maya layers (D-28) -------------------------------------------------------------------------------
def short_name(path: Optional[str]) -> str:
    return (path or "?").split("|")[-1]


def new_maya_layer(name: str, camera_uuid: Optional[str] = None, camera: Optional[str] = None,
                   objects: Optional[List[dict]] = None, layer_camera_uuid: Optional[str] = None,
                   layer_camera: Optional[str] = None) -> dict:
    return {"id": "ml-" + uuid.uuid4().hex[:12], "name": name or "Layer", "camera_uuid": camera_uuid,
            "camera": camera, "layer_camera_uuid": layer_camera_uuid, "layer_camera": layer_camera,
            "objects": list(objects or [])}


def driven_camera(layer: dict) -> dict:
    """{camera_uuid, camera} that the layer's links move: its dedicated camera (D-29), else the camera
    itself (layers moved from schema 1)."""
    if layer.get("layer_camera_uuid"):
        return {"camera_uuid": layer["layer_camera_uuid"], "camera": layer.get("layer_camera")}
    return {"camera_uuid": layer.get("camera_uuid"), "camera": layer.get("camera")}


def empty_store() -> dict:
    return {"maya_layers": [], "mappings": []}


def maya_layer(store: dict, layer_id: Optional[str]) -> Optional[dict]:
    for layer in store["maya_layers"]:
        if layer["id"] == layer_id:
            return layer
    return None


def layer_for_camera(store: dict, camera_uuid: str, camera: Optional[str] = None) -> dict:
    """The Maya layer using this camera; a new one (added to the store) when there is none."""
    for layer in store["maya_layers"]:
        if layer.get("camera_uuid") == camera_uuid:
            return layer
    layer = new_maya_layer(short_name(camera).replace("Shape", "") or "Layer", camera_uuid, camera)
    store["maya_layers"].append(layer)
    return layer


def set_layer_camera(store: dict, layer_id: str, camera_uuid: Optional[str], camera: Optional[str],
                     layer_camera_uuid: Optional[str] = None, layer_camera: Optional[str] = None) -> dict:
    """Change a Maya layer's camera (and its dedicated camera); its links follow (their references are
    dropped: they held the old camera's values)."""
    layer = maya_layer(store, layer_id)
    if layer is None:
        raise ValueError("no Maya layer %r" % layer_id)
    changed = layer.get("camera_uuid") != camera_uuid
    layer.update(camera_uuid=camera_uuid, camera=camera, layer_camera_uuid=layer_camera_uuid,
                 layer_camera=layer_camera)
    for m in links_of(store, layer_id):
        m["maya"] = dict(m.get("maya") or {}, **driven_camera(layer))
        if changed:
            m["reference"] = None
    return layer


def stack(store: dict) -> List[dict]:
    """The Maya layers to draw on top of each other in the layer stack view (D-32), bottom first:
    the layer listed first in the layer map is on top (like AE). Layers without a camera or without
    objects are left out. [{id, name, camera_uuid (the camera it is drawn with), original_camera_uuid
    (the layer's camera, for the comp frame), object_uuids}]"""
    out = []
    for layer in reversed(store["maya_layers"]):
        if not layer.get("visible", True):
            continue
        cam = driven_camera(layer)
        uuids = [o.get("uuid") for o in layer.get("objects") or [] if o.get("uuid")]
        if cam["camera_uuid"] and uuids:
            out.append({"id": layer["id"], "name": layer["name"], "camera_uuid": cam["camera_uuid"],
                        "original_camera_uuid": layer.get("camera_uuid") or cam["camera_uuid"],
                        "object_uuids": uuids})
    return out


def reorder_layers(store: dict, layer_ids: List[str]) -> None:
    """Put the Maya layers in this order (top / front first, the stacking order, D-33); layers not named
    keep their place after the named ones."""
    by_id = {layer["id"]: layer for layer in store["maya_layers"]}
    ordered = [by_id[i] for i in layer_ids if i in by_id]
    store["maya_layers"] = ordered + [layer for layer in store["maya_layers"] if layer["id"] not in layer_ids]


def set_layer_visible(store: dict, layer_id: str, visible: bool) -> dict:
    """Show / hide a Maya layer in the layer stack view (the eye of the viewer's layer list, D-33)."""
    layer = maya_layer(store, layer_id)
    if layer is None:
        raise ValueError("no Maya layer %r" % layer_id)
    layer["visible"] = bool(visible)
    return layer


def links_of(store: dict, layer_id: str) -> List[dict]:
    return [m for m in store["mappings"] if m.get("maya_layer") == layer_id]


def remove_maya_layer(store: dict, layer_id: str) -> int:
    """Remove a Maya layer and its links. Returns how many links went with it."""
    gone = links_of(store, layer_id)
    store["maya_layers"] = [layer for layer in store["maya_layers"] if layer["id"] != layer_id]
    store["mappings"] = [m for m in store["mappings"] if m.get("maya_layer") != layer_id]
    return len(gone)


def connect(store: dict, ae: dict, layer_id: str, method: str = "pan_zoom", mode: str = "relative",
            bg: Optional[dict] = None, name: Optional[str] = None) -> dict:
    """Link an AE layer to a Maya layer (the node editor's wire). An AE layer has one link: an existing
    link of the same AE layer is moved to this Maya layer (its reference is dropped)."""
    layer = maya_layer(store, layer_id)
    if layer is None:
        raise ValueError("no Maya layer %r" % layer_id)
    if not layer.get("camera_uuid"):
        raise ValueError(u"Maya レイヤー「%s」にカメラがありません。先にカメラを選んでください。" % layer["name"])
    maya = driven_camera(layer)
    if bg:
        maya.update(bg_uuid=bg.get("uuid"), bg=bg.get("name"))
    old = find(store["mappings"], ae)
    if old is not None:
        old.update(maya_layer=layer_id, maya=dict(old.get("maya") or {}, **maya), reference=None)
        return old
    link = new_mapping(ae, maya, method, name, mode)
    link["maya_layer"] = layer_id
    store["mappings"].append(link)
    return link


def disconnect(store: dict, mapping_id: str) -> None:
    store["mappings"] = [m for m in store["mappings"] if m["id"] != mapping_id]


def load_store(data) -> dict:
    """The store from the stored JSON value; schema 1 (links only) gets one Maya layer per camera."""
    if not data:
        return empty_store()
    if data.get("schema_version", 1) > SCHEMA_VERSION:
        raise ValueError(u"新しい SyncBridge で保存された対応付けです（schema_version %s）。SyncBridge を更新してください。"
                         % data.get("schema_version"))
    store = {"maya_layers": [dict(layer) for layer in data.get("maya_layers") or []],
             "mappings": [dict(m) for m in data.get("mappings") or []]}
    for m in store["mappings"]:
        if not m.get("maya_layer") or maya_layer(store, m["maya_layer"]) is None:
            cam = (m.get("maya") or {})
            m["maya_layer"] = layer_for_camera(store, cam.get("camera_uuid"), cam.get("camera"))["id"]
    return store


def dump_store(store: dict) -> Dict[str, object]:
    return {"schema_version": SCHEMA_VERSION, "maya_layers": list(store["maya_layers"]),
            "mappings": list(store["mappings"])}


# -- links --------------------------------------------------------------------------------------------
def new_mapping(ae: dict, maya: dict, method: str = "film_offset", name: Optional[str] = None,
                mode: str = "absolute") -> dict:
    if method not in METHODS:
        raise ValueError("method must be one of %s" % (METHODS,))
    if mode not in MODES:
        raise ValueError("mode must be one of %s" % (MODES,))
    for key in ("camera_uuid", "bg_uuid") if mode == "absolute" else ("camera_uuid",):
        if not maya.get(key):
            raise ValueError("maya.%s is required" % key)
    return {
        "id": "vl-" + uuid.uuid4().hex[:12],
        "name": name or ae.get("layer") or "BG",
        "ae": {k: ae.get(k) for k in ("comp_id", "comp", "layer_id", "layer", "source", "source_width",
                                      "source_height")},
        "maya": {k: maya.get(k) for k in ("camera_uuid", "camera", "bg_uuid", "bg")},
        "enabled": True,
        "direction": "ae2maya",
        "properties": ["pan"],
        "method": method,
        "mode": mode,
        "reference": None,
    }


def mode_of(mapping: dict) -> str:
    return mapping.get("mode") or "absolute"          # records made before D-25 are absolute


def with_reference(mapping: dict, matrix, camera_values: dict, comp_time=None) -> dict:
    """A copy of a relative record whose reference is the AE layer's matrix and the camera values now."""
    return dict(mapping, reference={"matrix": [list(row) for row in matrix], "camera": dict(camera_values),
                                    "comp_time": comp_time})


def with_method(mapping: dict, method: str) -> dict:
    """A copy using another method; a relative record takes a new reference at the next send (the old
    reference holds the old method's camera values)."""
    if method not in METHODS:
        raise ValueError("method must be one of %s" % (METHODS,))
    out = dict(mapping, method=method)
    if mode_of(mapping) == "relative":
        out["reference"] = None
    return out


def with_mode(mapping: dict, mode: str, bg: Optional[dict] = None) -> dict:
    """A copy in another mode; absolute needs a BG mesh ({uuid, name}, or the one recorded before).
    The reference is dropped either way."""
    if mode not in MODES:
        raise ValueError("mode must be one of %s" % (MODES,))
    maya = dict(mapping.get("maya") or {})
    if bg:
        maya.update(bg_uuid=bg.get("uuid"), bg=bg.get("name"))
    if mode == "absolute" and not maya.get("bg_uuid"):
        raise ValueError(u"絶対モードには BG の板ポリが要ります。Maya で板ポリを選んでから切り替えてください。")
    return dict(mapping, mode=mode, maya=maya, reference=None)


def without_reference(mapping: dict) -> dict:
    """The next send records a new reference (and changes nothing)."""
    return dict(mapping, reference=None)


def matches(mapping: dict, ae_layer: dict) -> bool:
    """Does this record belong to the AE layer described by `ae_layer` ({comp_id, comp, layer_id, layer})?"""
    rec = mapping["ae"]
    if rec.get("layer_id") is not None and ae_layer.get("layer_id") is not None:
        return rec["layer_id"] == ae_layer["layer_id"] and rec.get("comp_id") == ae_layer.get("comp_id")
    return rec.get("comp") == ae_layer.get("comp") and rec.get("layer") == ae_layer.get("layer")


def find(mappings: List[dict], ae_layer: dict) -> Optional[dict]:
    for m in mappings:
        if matches(m, ae_layer):
            return m
    return None


def camera_conflicts(mappings: List[dict], mapping: dict) -> List[dict]:
    """Other enabled records that move the same Maya camera with the same method: one camera cannot
    take two different offsets at once (spec 4.2)."""
    out = []
    for m in mappings:
        if m["id"] == mapping["id"] or not m.get("enabled", True):
            continue
        if m["maya"].get("camera_uuid") == mapping["maya"].get("camera_uuid") and m["method"] == mapping["method"]:
            out.append(m)
    return out


def upsert(mappings: List[dict], mapping: dict) -> List[dict]:
    """A new list with `mapping` replacing the record with its id (or appended)."""
    out = [m for m in mappings if m["id"] != mapping["id"]]
    out.append(mapping)
    return out


def remove(mappings: List[dict], mapping_id: str) -> List[dict]:
    return [m for m in mappings if m["id"] != mapping_id]


def load(data) -> List[dict]:
    """The links of the stored JSON value (see load_store)."""
    return load_store(data)["mappings"]


def dump(mappings: List[dict], maya_layers: Optional[List[dict]] = None) -> Dict[str, object]:
    store = {"maya_layers": list(maya_layers or []), "mappings": list(mappings)}
    for m in store["mappings"]:                      # links without a Maya layer get one per camera
        if not m.get("maya_layer") or maya_layer(store, m["maya_layer"]) is None:
            cam = m.get("maya") or {}
            m["maya_layer"] = layer_for_camera(store, cam.get("camera_uuid"), cam.get("camera"))["id"]
    return dump_store(store)


def describe(mapping: dict) -> str:
    """'BG Slide: AE c010 / BG -> BG_CAMShape (Film Offset)'"""
    labels = {"film_offset": "Film Offset", "film_translate": "Film Translate", "pan_zoom": "2D Pan/Zoom",
              "film_roll": u"Film Translate・Scale・Roll"}
    cam = (mapping["maya"].get("camera") or "?").split("|")[-1]
    mode = mode_of(mapping)
    extra = ""
    if mode == "relative" and not mapping.get("reference"):
        extra = u"［基準なし: 次の送信で基準を記録］"
    return u"%s: AE %s / %s → %s（%s・%s）%s%s" % (
        mapping.get("name", ""), mapping["ae"].get("comp") or "?", mapping["ae"].get("layer") or "?", cam,
        MODE_LABELS[mode], labels.get(mapping["method"], mapping["method"]), extra,
        "" if mapping.get("enabled", True) else u"［無効］")


def ae_from_layers_info(comp: dict, layer: dict) -> dict:
    """The `ae` of a link from SBCep.layersInfo() (its comp and one of its layers)."""
    return {"comp_id": comp.get("id"), "comp": comp.get("name"), "layer_id": layer.get("id"),
            "layer": layer.get("name"), "source": layer.get("source"), "source_width": layer.get("width"),
            "source_height": layer.get("height")}


def ae_layer_from_export(data: dict):
    """(transform for core.pixel_mapping.ae_layer_matrix, warnings) from SBCep.pixelMapInfo().

    Effects are not refused: which ones change the geometry is not known from their names here, so
    the user is told that a geometry-changing effect would put the BG elsewhere (spec 6)."""
    layer = data["layer"]
    warnings = []
    effects = layer.get("effects") or []
    if effects:
        warnings.append(u"レイヤーにエフェクトがあります（%s）。形や位置を変えるエフェクトなら、Maya の位置は合いません。"
                        % ", ".join(effects))
    transform = {"position": layer["position"], "anchorPoint": layer["anchorPoint"], "scale": layer.get("scale"),
                 "rotation": layer.get("rotation", 0.0), "threeD": layer.get("threeD", False),
                 "parent": layer.get("parent")}
    return transform, warnings
