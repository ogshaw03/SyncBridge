"""Virtual Layer Mapping (Pixel Mapping Phase 2, docs/PIXEL_MAPPING.md, D-24).

A virtual layer ties one AE layer to one Maya camera (and the BG mesh it looks at). It is SyncBridge's
own record, separate from Maya's display / render layers. The records are kept in the Maya scene
(syncbridge_maya.layer_mapping), so they travel with the scene to another PC.

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
    }

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
SCHEMA_VERSION = 1


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
    """Records from the stored JSON value ({"schema_version", "mappings"}); [] for nothing stored."""
    if not data:
        return []
    if data.get("schema_version", SCHEMA_VERSION) > SCHEMA_VERSION:
        raise ValueError(u"新しい SyncBridge で保存された対応付けです（schema_version %s）。SyncBridge を更新してください。"
                         % data.get("schema_version"))
    return list(data.get("mappings") or [])


def dump(mappings: List[dict]) -> Dict[str, object]:
    return {"schema_version": SCHEMA_VERSION, "mappings": list(mappings)}


def describe(mapping: dict) -> str:
    """'BG Slide: AE c010 / BG -> BG_CAMShape (Film Offset)'"""
    labels = {"film_offset": "Film Offset", "film_translate": "Film Translate", "pan_zoom": "2D Pan/Zoom"}
    cam = (mapping["maya"].get("camera") or "?").split("|")[-1]
    mode = mode_of(mapping)
    extra = ""
    if mode == "relative" and not mapping.get("reference"):
        extra = u"［基準なし: 次の送信で基準を記録］"
    return u"%s: AE %s / %s → %s（%s・%s）%s%s" % (
        mapping.get("name", ""), mapping["ae"].get("comp") or "?", mapping["ae"].get("layer") or "?", cam,
        MODE_LABELS[mode], labels.get(mapping["method"], mapping["method"]), extra,
        "" if mapping.get("enabled", True) else u"［無効］")


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
