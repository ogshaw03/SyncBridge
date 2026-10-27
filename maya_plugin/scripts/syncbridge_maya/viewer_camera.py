"""The viewer camera (D-44): what the SyncBridge viewer's panel looks through while a layer is edited.

It is a child of the editing layer's dedicated camera (D-29), at its origin and locked, so it follows the
camera work. The lens, film back, film translate, post-scale and roll are connected from the dedicated
camera; its film offset and pre-scale take the dedicated camera's 2D pan / zoom folded in
(core.stack_view.fold_pan_zoom, by utility nodes, so animated values follow). Its own 2D pan / zoom
belong to the view: Maya's 2D Pan/Zoom tool changes them (the user, 2026-10-27), and the viewer draws
the other layers and the comp frame with the same pan / zoom.

Because the panel looks through this camera, Maya's own selection and manipulators work in the editing
layer's picture (H-MY-38). The nodes are not saved with the scene (doNotWrite) and not in the undo queue;
the viewer deletes them when it closes.

    shape = viewer_camera.ensure(dedicated_camera_shape)
    viewer_camera.view(shape) -> (hpan, vpan, zoom);  viewer_camera.set_view(shape, 0, 0, 1.2)
    viewer_camera.remove()
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import maya.api.OpenMaya as om2
from maya import cmds

from . import layer_camera

NAME = "SB_VIEWER_CAM"
MARK_ATTR = "syncBridgeViewer"          # on every node made here
DIRECT_ATTRS = layer_camera.LINKED_ATTRS + (
    "filmTranslateH", "filmTranslateV", "postScale", "filmRollValue", "horizontalRollPivot",
    "verticalRollPivot", "filmRollOrder")


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
    with _no_undo():
        cmds.setAttr(shape + ".horizontalPan", hpan)
        cmds.setAttr(shape + ".verticalPan", vpan)
        cmds.setAttr(shape + ".zoom", max(1e-4, float(zoom)))
        cmds.setAttr(shape + ".panZoomEnabled", True)


class _no_undo(object):
    """The viewer camera is the view's, not the scene's: keep it out of the undo queue."""

    def __enter__(self):
        self.state = cmds.undoInfo(q=True, stateWithoutFlush=True)
        cmds.undoInfo(stateWithoutFlush=False)

    def __exit__(self, *exc):
        cmds.undoInfo(stateWithoutFlush=self.state)
        return False


def ensure(dedicated: str, initial_zoom: float = 1.0) -> str:
    """The viewer camera under the dedicated camera `dedicated` (shape or transform); made, or moved there
    keeping the view's pan / zoom. Returns its shape."""
    dedicated = layer_camera._shape(dedicated)
    old = current()
    if old and followed(old) == dedicated:
        if not cmds.getAttr(old + ".renderPanZoom"):          # made by the first version (H-MY-41)
            with _no_undo():
                cmds.setAttr(old + ".renderPanZoom", True)
        return old
    kept = view(old) if old else (0.0, 0.0, initial_zoom)
    with _no_undo():
        remove()
        shape = _create(dedicated)
    set_view(shape, *kept)
    return shape


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
    for attr in DIRECT_ATTRS:
        cmds.connectAttr("%s.%s" % (dedicated, attr), "%s.%s" % (shape, attr), force=True)
    _fold(dedicated, shape)
    try:
        cmds.camera(tr, e=True, lockTransform=True)        # tumble / dolly would leave the dedicated camera
    except Exception:                                      # not in every Maya version: the transform is locked
        pass
    return shape


def _fold(dedicated: str, shape: str) -> None:
    """film offset' = film offset + 2D pan (when enabled), pre-scale' = pre-scale / zoom (when enabled)."""
    pan = cmds.createNode("multiplyDivide", name="SB_VIEWER_pan")              # pan * enabled
    offset = cmds.createNode("plusMinusAverage", name="SB_VIEWER_offset")      # film offset + that
    zoom = cmds.createNode("condition", name="SB_VIEWER_zoom")                 # enabled ? zoom : 1
    scale = cmds.createNode("multiplyDivide", name="SB_VIEWER_prescale")       # pre-scale / that
    for node in (pan, offset, zoom, scale):
        _mark(node)
    src = dedicated + "."
    cmds.connectAttr(src + "horizontalPan", pan + ".input1X")
    cmds.connectAttr(src + "verticalPan", pan + ".input1Y")
    cmds.connectAttr(src + "panZoomEnabled", pan + ".input2X")
    cmds.connectAttr(src + "panZoomEnabled", pan + ".input2Y")
    cmds.connectAttr(src + "horizontalFilmOffset", offset + ".input2D[0].input2Dx")
    cmds.connectAttr(src + "verticalFilmOffset", offset + ".input2D[0].input2Dy")
    cmds.connectAttr(pan + ".outputX", offset + ".input2D[1].input2Dx")
    cmds.connectAttr(pan + ".outputY", offset + ".input2D[1].input2Dy")
    cmds.connectAttr(offset + ".output2Dx", shape + ".horizontalFilmOffset")
    cmds.connectAttr(offset + ".output2Dy", shape + ".verticalFilmOffset")
    cmds.connectAttr(src + "panZoomEnabled", zoom + ".firstTerm")
    cmds.setAttr(zoom + ".secondTerm", 1.0)
    cmds.setAttr(zoom + ".operation", 0)                                       # equal
    cmds.connectAttr(src + "zoom", zoom + ".colorIfTrueR")
    cmds.setAttr(zoom + ".colorIfFalseR", 1.0)
    cmds.setAttr(scale + ".operation", 2)                                      # divide
    cmds.connectAttr(src + "preScale", scale + ".input1X")
    cmds.connectAttr(zoom + ".outColorR", scale + ".input2X")
    cmds.connectAttr(scale + ".outputX", shape + ".preScale")


def remove() -> None:
    """Delete the viewer camera and its utility nodes."""
    with _no_undo():
        nodes = [n for n in _nodes() if cmds.objExists(n)]
        tops = [n for n in nodes if cmds.nodeType(n) != "camera"]
        if tops:
            cmds.delete(tops)
