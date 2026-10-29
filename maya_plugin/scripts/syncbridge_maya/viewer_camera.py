"""The viewer camera (D-44): what the SyncBridge viewer's panel looks through while a layer is edited.

It is a child of the editing layer's dedicated camera (D-29), at its origin and locked, so it follows the
camera work. The lens, film back, post-scale and roll are connected from the dedicated camera; its film
offset and pre-scale take the dedicated camera's 2D pan / zoom folded in (core.stack_view.fold_pan_zoom, by
utility nodes, so animated values follow). Its own 2D pan / zoom belong to the view: Maya's 2D Pan/Zoom tool
changes them (the user, 2026-10-27), and the viewer draws the other layers and the comp frame with the same
pan / zoom. Its film translate is the dedicated camera's, changed by an expression so that the 2D pan / zoom
stays a fixed view while the layer's film translate / roll / post-scale are animated
(core.stack_view.steady_translate, D-48): Maya applies the 2D pan / zoom before them (H-PM-8).

Because the panel looks through this camera, Maya's own selection and manipulators work in the editing
layer's picture (H-MY-38). The nodes are not saved with the scene (doNotWrite) and not in the undo queue;
the viewer deletes them when it closes.

    shape = viewer_camera.ensure(dedicated_camera_shape)
    viewer_camera.view(shape) -> (hpan, vpan, zoom);  viewer_camera.set_view(shape, 0, 0, 1.2)
    viewer_camera.remove()
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

import maya.api.OpenMaya as om2
from maya import cmds

from . import layer_camera

NAME = "SB_VIEWER_CAM"
MARK_ATTR = "syncBridgeViewer"          # on every node made here
# Not "orthographic": linking it again when the viewer camera moves to another layer made the panel
# re-read it while its camera was being set, and Maya 2024 crashed (TmodelPane::cameraOrthographicModified,
# 2026-10-27). The stack draws perspective cameras only; the value is copied instead.
DIRECT_ATTRS = tuple(a for a in layer_camera.LINKED_ATTRS if a != "orthographic") + (
    "postScale", "filmRollValue", "horizontalRollPivot", "verticalRollPivot", "filmRollOrder")

# The steady view (D-48): the inputs of core.stack_view.steady_translate on one node (a DG node, so the
# expression names it without a DAG path), from the dedicated camera and from the viewer camera.
STEADY_FROM_DEDICATED = (("filmTranslateH", "ftH"), ("filmTranslateV", "ftV"), ("filmRollValue", "roll"),
                         ("horizontalRollPivot", "pivotH"), ("verticalRollPivot", "pivotV"),
                         ("filmRollOrder", "order"), ("postScale", "post"))
STEADY_FROM_VIEWER = (("horizontalPan", "panH"), ("verticalPan", "panV"), ("zoom", "zoom"),
                      ("panZoomEnabled", "enabled"), ("preScale", "pre"), ("horizontalFilmAperture", "hfa"),
                      ("verticalFilmAperture", "vfa"), ("filmFit", "fit"), ("orthographic", "ortho"))
# The same formula as core.stack_view.steady_translate (tests/unit/test_stack_view.py; tools/maya_viewer_
# steady_check.py compares the two in mayapy). Made with unitConversion "none": the roll is read in radians.
# viewAspect is the view's width / height (set_view_aspect), which the pan's units depend on unless the film
# fit is horizontal.
STEADY_EXPRESSION = """
float $k = 1.0;
float $qh = 0.0;
float $qv = 0.0;
if (N.enabled) {
    float $z = N.zoom;
    if ($z == 0) $z = 1.0;
    $k = 1.0 / $z;
    if (!N.ortho) {
        float $device = N.viewAspect;
        float $film = N.hfa / N.vfa;
        int $fit = N.fit;
        float $half = N.vfa * $device / 2.0;
        if ($fit == 1 || ($fit == 0 && $film <= $device) || ($fit == 3 && $film > $device))
            $half = N.hfa / 2.0;
        $qh = N.panH * N.pre / $half;
        $qv = N.panV * N.pre / $half;
    }
}
float $post = N.post;
if ($post == 0) $post = 1.0;
float $c = cos(-N.roll);
float $s = sin(-N.roll);
float $ph = N.pivotH;
float $pv = N.pivotV;
if (N.order == 1) {
    float $ih = $c * $ph + $s * $pv;
    float $iv = -$s * $ph + $c * $pv;
    float $rh = $c * $qh + $s * $qv;
    float $rv = -$s * $qh + $c * $qv;
    N.outH = (1 - $k) * ($ih - $ph) + $k * N.ftH - $k * $qh + $k * $rh / $post;
    N.outV = (1 - $k) * ($iv - $pv) + $k * N.ftV - $k * $qv + $k * $rv / $post;
} else {
    float $rh = $c * $ph - $s * $pv;
    float $rv = $s * $ph + $c * $pv;
    float $th = $c * $qh - $s * $qv;
    float $tv = $s * $qh + $c * $qv;
    N.outH = (1 - $k) * ($ph - $rh) + $k * N.ftH - $k * $th + $k * $qh / $post;
    N.outV = (1 - $k) * ($pv - $rv) + $k * N.ftV - $k * $tv + $k * $qv / $post;
}
"""


def _mark(node: str) -> None:
    cmds.addAttr(node, longName=MARK_ATTR, attributeType="bool")
    sel = om2.MSelectionList()
    sel.add(node)
    om2.MFnDependencyNode(sel.getDependNode(0)).setDoNotWrite(True)    # never saved with the scene


def _nodes() -> List[str]:
    return cmds.ls("*." + MARK_ATTR, objectsOnly=True, long=True, recursive=True) or []


def current() -> Optional[str]:
    """The viewer camera's shape, or None."""
    for node in _nodes():
        shapes = cmds.listRelatives(node, shapes=True, type="camera", fullPath=True) or []
        if shapes:
            return shapes[0]
    return None


def followed(shape: str) -> Optional[str]:
    """The dedicated camera (shape) the viewer camera follows."""
    parent = cmds.listRelatives(cmds.listRelatives(shape, parent=True, fullPath=True)[0], parent=True,
                                fullPath=True)
    if not parent:
        return None
    shapes = cmds.listRelatives(parent[0], shapes=True, type="camera", fullPath=True) or []
    return shapes[0] if shapes else None


def view(shape: str) -> Tuple[float, float, float]:
    """The view's 2D pan / zoom (what Maya's 2D Pan/Zoom tool changed)."""
    return (cmds.getAttr(shape + ".horizontalPan"), cmds.getAttr(shape + ".verticalPan"),
            cmds.getAttr(shape + ".zoom"))


def set_view(shape: str, hpan: float, vpan: float, zoom: float) -> None:
    """2D Pan/Zoom is turned off when the view is the camera's own (no margin, no pan / zoom): Maya
    shows "2D Pan/Zoom" in the view while it is on (the user, 2026-10-27)."""
    zoom = max(1e-4, float(zoom))
    with _no_undo():
        cmds.setAttr(shape + ".horizontalPan", hpan)
        cmds.setAttr(shape + ".verticalPan", vpan)
        cmds.setAttr(shape + ".zoom", zoom)
        cmds.setAttr(shape + ".panZoomEnabled", not is_identity(hpan, vpan, zoom))


def is_identity(hpan: float, vpan: float, zoom: float, tol: float = 1e-6) -> bool:
    return abs(hpan) < tol and abs(vpan) < tol and abs(zoom - 1.0) < tol


_JOBS: List[int] = []


def _watch(shape: str) -> None:
    """Turn 2D Pan/Zoom on / off when its values change: Maya's panZoom left it off (mayapy and GUI
    Maya 2023 / 2024, 2026-10-27), and then the 2D Pan/Zoom tool would not move the view (H-MY-43)."""
    _unwatch()

    def follow():
        try:
            s = current()
            if s:
                on = not is_identity(*view(s))
                if bool(cmds.getAttr(s + ".panZoomEnabled")) != on:
                    with _no_undo():
                        cmds.setAttr(s + ".panZoomEnabled", on)
        except Exception:                    # never break Maya's own tool
            pass

    jobs = [(attr, follow) for attr in ("horizontalPan", "verticalPan", "zoom")]
    jobs += [(attr, _block_gates) for attr in GATE_ATTRS]
    for attr, fn in jobs:
        try:
            _JOBS.append(cmds.scriptJob(attributeChange=[shape + "." + attr, fn], killWithScene=True))
        except RuntimeError:                 # mayapy has no scriptJob event loop
            pass


# Maya's gates turn the overscan to 1.3 and draw the camera's own frame, which the stack does not use
# (the viewer draws Maya's render resolution itself, D-27 / D-34): they are kept off (the user, 2026-10-27).
GATE_ATTRS = ("displayResolution", "displayFilmGate")
GATE_MESSAGE = (u"SyncBridge ビューアーでは解像度ゲート・フィルムゲートは使えません"
                u"（レイヤーが枠からずれるため）。上の「解像度の枠」を使ってください。")
gate_listeners: List = []                  # the viewer shows the message in its status line too


def _block_gates() -> None:
    try:
        s = current()
        if not s or not any(cmds.getAttr(s + "." + a) for a in GATE_ATTRS):
            return
        with _no_undo():
            for attr in GATE_ATTRS:
                cmds.setAttr(s + "." + attr, False)
            cmds.setAttr(s + ".overscan", 1.0)
        cmds.warning(GATE_MESSAGE)
        try:
            cmds.inViewMessage(assistMessage=GATE_MESSAGE, position="midCenter", fade=True)
        except Exception:
            pass
        for fn in list(gate_listeners):
            fn(GATE_MESSAGE)
    except Exception:                        # never break Maya's own button
        pass


def _unwatch() -> None:
    while _JOBS:
        job = _JOBS.pop()
        if job is not None and cmds.scriptJob(exists=job):       # scriptJob gives None in mayapy
            cmds.scriptJob(kill=job, force=True)


class _no_undo(object):
    """The viewer camera is the view's, not the scene's: keep it out of the undo queue."""

    def __enter__(self):
        self.state = cmds.undoInfo(q=True, stateWithoutFlush=True)
        cmds.undoInfo(stateWithoutFlush=False)

    def __exit__(self, *exc):
        cmds.undoInfo(stateWithoutFlush=self.state)
        return False


class _keep_selection(object):
    """Maya's parent, camera and createNode select what they made or moved (H-MY-44): the viewer camera
    took the user's selection whenever the editing layer changed (P-11, 2026-10-28). The selection is put
    back as it was, in its order (the manipulator is at the last one), outside the undo queue."""

    def __enter__(self):
        self.saved = cmds.ls(selection=True, long=True) or []

    def __exit__(self, *exc):
        keep = [n for n in self.saved if cmds.objExists(n) and not _is_viewer(n)]
        with _no_undo():
            if keep:
                cmds.select(keep, replace=True, noExpand=True)
            else:
                cmds.select(clear=True)
        return False


def _is_viewer(node: str) -> bool:
    try:
        return bool(cmds.attributeQuery(MARK_ATTR, node=node.split(".")[0], exists=True))
    except RuntimeError:
        return False


def ensure(dedicated: str, initial_zoom: float = 1.0) -> str:
    """The viewer camera under the dedicated camera `dedicated` (shape or transform); made, or moved there
    keeping the view's pan / zoom. Returns its shape. The selection is not changed.

    Moved, not made again: deleting it left the panel and the layer stack on a camera that was gone until
    the next refresh, and the view flickered on every change of the editing layer (the user, 2026-10-27)."""
    with _keep_selection():
        return _ensure(dedicated, initial_zoom)


def _ensure(dedicated: str, initial_zoom: float) -> str:
    dedicated = layer_camera._shape(dedicated)
    old = current()
    if old is not None and _steady_node(old) is None:          # made by a version without the steady view
        remove()
        old = None
    if old is None:
        with _no_undo():
            shape = _create(dedicated)
        set_view(shape, 0.0, 0.0, initial_zoom)
        _watch(shape)
        return shape
    moved = followed(old) != dedicated
    with _no_undo():
        if moved:
            _follow(old, dedicated)
            old = current()
        if not cmds.getAttr(old + ".renderPanZoom"):          # made by the first version (H-MY-41)
            cmds.setAttr(old + ".renderPanZoom", True)
    if moved or not _JOBS:                                    # watched by its new path
        _watch(old)
    return old


def _follow(shape: str, dedicated: str) -> None:
    """Put the viewer camera under another dedicated camera and take its values from that one."""
    nodes = _fold_nodes(shape)
    tr = cmds.listRelatives(shape, parent=True, fullPath=True)[0]
    _lock(tr, False)                                       # a locked camera's attributes cannot be connected
    tr = cmds.ls(cmds.parent(tr, layer_camera._transform(dedicated), relative=True)[0], long=True)[0]
    shape = cmds.listRelatives(tr, shapes=True, type="camera", fullPath=True)[0]
    _link(dedicated, shape, nodes)
    _lock(tr, True)


def _lock(tr: str, locked: bool) -> None:
    try:
        cmds.camera(tr, e=True, lockTransform=locked)       # tumble / dolly would leave the dedicated camera
    except Exception:                                      # not in every Maya version: the transform is locked
        pass


def _source(plug: str) -> str:
    return cmds.listConnections(plug, source=True, destination=False, skipConversionNodes=True)[0]


def _fold_nodes(shape: str) -> dict:
    """The utility nodes _fold made for this viewer camera, found by their connections."""
    offset = _source(shape + ".horizontalFilmOffset")
    scale = _source(shape + ".preScale")
    return {"pan": _source(offset + ".input2D[1].input2Dx"), "offset": offset,
            "zoom": _source(scale + ".input2X"), "scale": scale, "steady": _steady_node(shape)}


def _steady_node(shape: str) -> Optional[str]:
    """The node of the steady view (D-48), or None (a viewer camera of an earlier version)."""
    sources = cmds.listConnections(shape + ".filmTranslateH", source=True, destination=False,
                                   skipConversionNodes=True) or []
    if sources and cmds.attributeQuery("viewAspect", node=sources[0], exists=True):
        return sources[0]
    return None


def set_view_aspect(aspect: float, shape: Optional[str] = None) -> None:
    """The view's width / height, for the steady view's pan (D-48). Unchanged values are not set again."""
    shape = shape or current()
    node = _steady_node(shape) if shape else None
    if node is None or aspect <= 0:
        return
    if abs(cmds.getAttr(node + ".viewAspect") - float(aspect)) > 1e-9:
        with _no_undo():
            cmds.setAttr(node + ".viewAspect", float(aspect))


def _create(dedicated: str) -> str:
    tr = cmds.camera()[0]
    tr = cmds.parent(tr, layer_camera._transform(dedicated), relative=True)[0]
    tr = cmds.ls(cmds.rename(tr, NAME), long=True)[0]
    shape = cmds.listRelatives(tr, shapes=True, type="camera", fullPath=True)[0]
    shape = cmds.ls(cmds.rename(shape, tr.split("|")[-1] + "Shape"), long=True)[0]
    for node in (tr, shape):
        _mark(node)
    layer_camera._place(tr)
    cmds.setAttr(tr + ".hiddenInOutliner", True)
    cmds.setAttr(shape + ".renderable", False)
    cmds.setAttr(shape + ".overscan", 1.0)                # H-PM-10: 1.0, like the dedicated cameras
    # On: the layer stack's pass draws through this camera with the camera's own projection, which leaves
    # the 2D pan / zoom out unless renderPanZoom is on (the user, 2026-10-27: the editing layer was not
    # zoomed while the view, its frame and the other layers were; H-MY-41). It is never rendered.
    cmds.setAttr(shape + ".renderPanZoom", True)
    _link(dedicated, shape, _fold(shape))
    _lock(tr, True)
    return shape


def _fold(shape: str) -> dict:
    """film offset' = film offset + 2D pan (when enabled), pre-scale' = pre-scale / zoom (when enabled):
    the utility nodes and their links to the viewer camera; _link connects the dedicated camera."""
    pan = cmds.createNode("multiplyDivide", name="SB_VIEWER_pan")              # pan * enabled
    offset = cmds.createNode("plusMinusAverage", name="SB_VIEWER_offset")      # film offset + that
    zoom = cmds.createNode("condition", name="SB_VIEWER_zoom")                 # enabled ? zoom : 1
    scale = cmds.createNode("multiplyDivide", name="SB_VIEWER_prescale")       # pre-scale / that
    for node in (pan, offset, zoom, scale):
        _mark(node)
    cmds.connectAttr(pan + ".outputX", offset + ".input2D[1].input2Dx")
    cmds.connectAttr(pan + ".outputY", offset + ".input2D[1].input2Dy")
    cmds.connectAttr(offset + ".output2Dx", shape + ".horizontalFilmOffset")
    cmds.connectAttr(offset + ".output2Dy", shape + ".verticalFilmOffset")
    cmds.setAttr(zoom + ".secondTerm", 1.0)
    cmds.setAttr(zoom + ".operation", 0)                                       # equal
    cmds.setAttr(zoom + ".colorIfFalseR", 1.0)
    cmds.setAttr(scale + ".operation", 2)                                      # divide
    cmds.connectAttr(zoom + ".outColorR", scale + ".input2X")
    cmds.connectAttr(scale + ".outputX", shape + ".preScale")
    return {"pan": pan, "offset": offset, "zoom": zoom, "scale": scale, "steady": _steady(shape)}


def _steady(shape: str) -> str:
    """The steady view (D-48): a node holding steady_translate's inputs and an expression that sets its
    outputs, which drive the viewer camera's film translate. _link connects the dedicated camera's side."""
    node = cmds.createNode("network", name="SB_VIEWER_steady", skipSelect=True)
    _mark(node)
    for _, attr in STEADY_FROM_DEDICATED + STEADY_FROM_VIEWER:
        if attr == "roll":
            cmds.addAttr(node, longName=attr, attributeType="doubleAngle")
        else:
            cmds.addAttr(node, longName=attr, attributeType="double")
    for attr in ("viewAspect", "outH", "outV"):
        cmds.addAttr(node, longName=attr, attributeType="double")
    cmds.setAttr(node + ".viewAspect", 16.0 / 9.0)               # set_view_aspect puts the view's own
    for source, attr in STEADY_FROM_VIEWER:
        cmds.connectAttr("%s.%s" % (shape, source), "%s.%s" % (node, attr))
    text = re.sub(r"\bN\.", node + ".", STEADY_EXPRESSION)
    expression = cmds.expression(name="SB_VIEWER_steadyExpression", string=text, unitConversion="none",
                                 alwaysEvaluate=True)
    _mark(expression)
    cmds.connectAttr(node + ".outH", shape + ".filmTranslateH", force=True)
    cmds.connectAttr(node + ".outV", shape + ".filmTranslateV", force=True)
    return node


def _link(dedicated: str, shape: str, nodes: dict) -> None:
    """Take the values from this dedicated camera (replacing the links to the one before)."""
    src = dedicated + "."
    for attr in DIRECT_ATTRS:
        cmds.connectAttr(src + attr, "%s.%s" % (shape, attr), force=True)
    orthographic = bool(cmds.getAttr(src + "orthographic"))
    linked = cmds.listConnections(shape + ".orthographic", source=True, destination=False)   # an older one
    if not linked and bool(cmds.getAttr(shape + ".orthographic")) != orthographic:
        cmds.setAttr(shape + ".orthographic", orthographic)
    pan, offset, zoom, scale = nodes["pan"], nodes["offset"], nodes["zoom"], nodes["scale"]
    for source, target in (("horizontalPan", pan + ".input1X"), ("verticalPan", pan + ".input1Y"),
                           ("panZoomEnabled", pan + ".input2X"), ("panZoomEnabled", pan + ".input2Y"),
                           ("horizontalFilmOffset", offset + ".input2D[0].input2Dx"),
                           ("verticalFilmOffset", offset + ".input2D[0].input2Dy"),
                           ("panZoomEnabled", zoom + ".firstTerm"), ("zoom", zoom + ".colorIfTrueR"),
                           ("preScale", scale + ".input1X")):
        cmds.connectAttr(src + source, target, force=True)
    for source, attr in STEADY_FROM_DEDICATED:
        cmds.connectAttr(src + source, "%s.%s" % (nodes["steady"], attr), force=True)


def remove() -> None:
    """Delete the viewer camera and its utility nodes (the selection is not changed)."""
    _unwatch()
    with _keep_selection(), _no_undo():
        nodes = [n for n in _nodes() if cmds.objExists(n)]
        tops = [n for n in nodes if cmds.nodeType(n) != "camera"]
        if tops:
            cmds.delete(tops)
