"""Which layer of the SyncBridge viewer is under a click (D-44).

The viewer draws every layer with its own camera (and the viewer's 2D pan / zoom), but Maya picks with
the panel's camera only: the viewer camera of the editing layer. A click on another layer is found here:
a ray from that layer's camera through the clicked point (core.stack_view.ray_direction), tested against
the meshes of the layer, top layer first. The viewer then makes that layer the editing one.

    hit = viewer_pick.pick(store, x, y, view_w, view_h)  -> {"layer": id, "node": transform} or None
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import maya.api.OpenMaya as om2
from maya import cmds

from syncbridge.core import layer_mapping as core_lm
from syncbridge.core import stack_view as core_view

from . import layer_mapping, layer_stack, pixel_mapping

MAX_DISTANCE = 1.0e7
NEAR_SELECTION_PX = 60.0       # a click this close to the selection's pivot is left to Maya (its manipulator)


def _dag(node: str):
    sel = om2.MSelectionList()
    sel.add(node)
    return sel.getDagPath(0)


def layer_affines(store: dict, view_w: float, view_h: float) -> List[Tuple[dict, str, tuple]]:
    """[(Maya layer, camera shape it is drawn with, (x/-z, y/-z) -> view NDC)] of the shown layers, top
    first, as the viewer draws them (the editing layer through the viewer camera)."""
    editing = layer_stack.editing()
    view = None
    if editing:
        view = core_view.view_affine(pixel_mapping.camera_data(editing[0]), pixel_mapping.camera_data(editing[1]),
                                     view_w, view_h)
    out = []
    for item in reversed(core_lm.stack(store)):          # stack() is bottom first
        camera = layer_mapping.node_by_uuid(item["camera_uuid"])
        if not camera:
            continue
        layer = core_lm.maya_layer(store, item["id"])
        if editing and camera == editing[0]:
            out.append((layer, editing[1], core_view.ndc_affine(pixel_mapping.camera_data(editing[1]), view_w, view_h)))
            continue
        cam = pixel_mapping.camera_data(camera)
        if cam["orthographic"]:
            continue
        affine = core_view.ndc_affine(cam, view_w, view_h)
        out.append((layer, camera, core_view.compose(view, affine) if view else affine))
    return out


def _meshes(node: str) -> List[str]:
    if cmds.nodeType(node) == "mesh":
        return [node]
    return [m for m in cmds.listRelatives(node, allDescendents=True, type="mesh", fullPath=True) or []
            if not cmds.getAttr(m + ".intermediateObject")]


def _visible(node: str) -> bool:
    try:
        return bool(cmds.ls(node, visible=True))
    except RuntimeError:
        return False


def hit_distance(mesh: str, source, direction) -> Optional[float]:
    """Distance along the ray to the mesh, or None (H-MY-39: MFnMesh.closestIntersection)."""
    fn = om2.MFnMesh(_dag(mesh))
    result = fn.closestIntersection(om2.MFloatPoint(source), om2.MFloatVector(direction), om2.MSpace.kWorld,
                                    MAX_DISTANCE, False)
    if not result:                                     # no hit: None (mayapy 2023)
        return None
    param, face = result[1], result[2]
    if face is None or face < 0 or param <= 0.0:
        return None
    return float(param)


def pick(store: dict, x: float, y: float, view_w: float, view_h: float) -> Optional[dict]:
    """The top layer whose meshes the ray through the view point (Qt pixels) hits."""
    ndc = core_view.pixel_to_ndc(x, y, view_w, view_h)
    for layer, camera, affine in layer_affines(store, view_w, view_h):
        u, v, w = core_view.ray_direction(affine, ndc)
        matrix = _dag(camera).inclusiveMatrix()
        source = om2.MPoint(0.0, 0.0, 0.0) * matrix
        direction = (om2.MVector(u, v, w) * matrix).normal()
        best = None
        for entry in layer.get("objects") or []:
            node = layer_mapping.node_by_uuid(entry.get("uuid"))
            if not node:
                continue
            for mesh in _meshes(node):
                if not _visible(mesh):
                    continue
                d = hit_distance(mesh, source, direction)
                if d is not None and (best is None or d < best[0]):
                    best = (d, cmds.listRelatives(mesh, parent=True, fullPath=True)[0])
        if best is not None:
            return {"layer": layer["id"], "node": best[1], "camera": camera}
    return None


def near_selection(store: dict, x: float, y: float, view_w: float, view_h: float) -> bool:
    """Is the click near the pivot of something selected in the editing layer (Maya's manipulator)?"""
    editing = layer_stack.editing()
    selected = cmds.ls(selection=True, long=True, transforms=True) or []
    if not editing or not selected:
        return False
    affine = core_view.ndc_affine(pixel_mapping.camera_data(editing[1]), view_w, view_h)
    inverse = _dag(editing[1]).inclusiveMatrixInverse()
    for node in selected:
        pivot = om2.MPoint(cmds.xform(node, q=True, worldSpace=True, rotatePivot=True)) * inverse
        if pivot.z >= 0:
            continue
        nx, ny = core_view.apply_affine(affine, (pivot.x, pivot.y, pivot.z))
        px, py = (nx + 1.0) * 0.5 * view_w, (1.0 - ny) * 0.5 * view_h
        if (px - x) ** 2 + (py - y) ** 2 <= NEAR_SELECTION_PX ** 2:
            return True
    return False
