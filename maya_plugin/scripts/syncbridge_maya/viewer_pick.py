"""Which layer of the SyncBridge viewer is under a click (D-44).

The viewer draws every layer with its own camera (and the viewer's 2D pan / zoom), but Maya picks with
the panel's camera only: the viewer camera of the editing layer. A click on another layer is found here:
a ray from that layer's camera through the clicked point (core.stack_view.ray_direction), tested against
the meshes of the layer, and its NURBS curves and locators as drawn in the view (a few pixels around them,
P-7), top layer first. The viewer then makes that layer the editing one.

    hit = viewer_pick.pick(store, x, y, view_w, view_h)  -> {"layer": id, "node": transform} or None
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

import maya.api.OpenMaya as om2
from maya import cmds

from syncbridge.core import layer_mapping as core_lm
from syncbridge.core import stack_view as core_view

from . import layer_mapping, layer_stack, pixel_mapping

MAX_DISTANCE = 1.0e7


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


def _nearest(nodes: List[str], camera: str, affine: tuple, ndc) -> Optional[str]:
    """The transform of the nearest visible mesh under `nodes` hit by the ray from `camera` through ndc."""
    u, v, w = core_view.ray_direction(affine, ndc)
    matrix = _dag(camera).inclusiveMatrix()
    source = om2.MPoint(0.0, 0.0, 0.0) * matrix
    direction = (om2.MVector(u, v, w) * matrix).normal()
    best = None
    for node in nodes:
        for mesh in _meshes(node):
            if not _visible(mesh):
                continue
            d = hit_distance(mesh, source, direction)
            if d is not None and (best is None or d < best[0]):
                best = (d, cmds.listRelatives(mesh, parent=True, fullPath=True)[0])
    return best[1] if best else None


CURVE_PX = 6.0            # a click this close to a drawn curve picks it (a 1 px line is hard to hit)
LOCATOR_PX = 10.0         # ... to a locator's centre
CURVE_SAMPLES = 64        # points along a curve, for its drawn line


def _shapes(node: str, kind: str) -> List[str]:
    if cmds.nodeType(node) == kind:
        return [node]
    return [s for s in cmds.listRelatives(node, allDescendents=True, type=kind, fullPath=True) or []
            if not cmds.getAttr(s + ".intermediateObject")]


def _to_pixel(point, inverse, affine: tuple, view_w: float, view_h: float):
    """A world point as the layer draws it (Qt pixels), or None behind its camera."""
    p = point * inverse
    if p.z >= 0.0:
        return None
    return core_view.ndc_to_pixel(core_view.apply_affine(affine, (p.x, p.y, p.z)), view_w, view_h)


def _nearest_line(nodes: List[str], camera: str, affine: tuple, x: float, y: float, view_w: float,
                  view_h: float) -> Optional[str]:
    """The transform of the visible NURBS curve or locator under `nodes` drawn nearest the view point,
    within CURVE_PX / LOCATOR_PX (rig controls: the ray of _nearest cannot hit a line, P-7, 2026-10-28)."""
    inverse = _dag(camera).inclusiveMatrixInverse()
    best = None
    for node in nodes:
        for shape in _shapes(node, "nurbsCurve"):
            if not _visible(shape):
                continue
            fn = om2.MFnNurbsCurve(_dag(shape))
            start, end = fn.knotDomain
            points = [_to_pixel(fn.getPointAtParam(start + (end - start) * i / CURVE_SAMPLES, om2.MSpace.kWorld),
                                inverse, affine, view_w, view_h) for i in range(CURVE_SAMPLES + 1)]
            d = core_view.polyline_distance((x, y), [p for p in points if p is not None])
            if d <= CURVE_PX and (best is None or d < best[0]):
                best = (d, cmds.listRelatives(shape, parent=True, fullPath=True)[0])
        for shape in _shapes(node, "locator"):
            if not _visible(shape):
                continue
            p = _to_pixel(om2.MPoint(cmds.getAttr(shape + ".worldPosition[0]")[0]), inverse, affine, view_w, view_h)
            d = math.hypot(p[0] - x, p[1] - y) if p is not None else math.inf
            if d <= LOCATOR_PX and (best is None or d < best[0]):
                best = (d, cmds.listRelatives(shape, parent=True, fullPath=True)[0])
    return best[1] if best else None


def pick(store: dict, x: float, y: float, view_w: float, view_h: float) -> Optional[dict]:
    """The top layer with a mesh the ray through the view point (Qt pixels) hits, or a curve / locator
    drawn near it. In a layer, a curve or locator wins over the mesh: rig controls lie on the body."""
    ndc = core_view.pixel_to_ndc(x, y, view_w, view_h)
    for layer, camera, affine in layer_affines(store, view_w, view_h):
        nodes = [n for n in (layer_mapping.node_by_uuid(entry.get("uuid")) for entry in layer.get("objects") or [])
                 if n]
        node = (_nearest_line(nodes, camera, affine, x, y, view_w, view_h)
                or _nearest(nodes, camera, affine, ndc))
        if node is not None:
            return {"layer": layer["id"], "node": node, "camera": camera}
    return None


def on_selection(x: float, y: float, view_w: float, view_h: float) -> bool:
    """Is a selected mesh under the view point as the panel's camera (the viewer camera) sees it? Then a
    click there that kept the selection was Maya selecting it again, not a click on the manipulator."""
    editing = layer_stack.editing()
    selected = cmds.ls(selection=True, long=True, transforms=True) or []
    if not editing or not selected:
        return False
    affine = core_view.ndc_affine(pixel_mapping.camera_data(editing[1]), view_w, view_h)
    return _nearest(selected, editing[1], affine, core_view.pixel_to_ndc(x, y, view_w, view_h)) is not None

