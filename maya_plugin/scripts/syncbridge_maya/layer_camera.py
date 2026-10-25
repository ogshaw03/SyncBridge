"""Dedicated cameras of the Maya layers (D-29): one camera per SyncBridge Maya layer, a child of the
camera the layer uses, so the layers can play different 2D offsets at the same time.

    shape = layer_camera.create("|SHOT_CAM|SHOT_CAMShape", "BG", layer_id)
        -> |SHOT_CAM|SB_BG_CAM|SB_BG_CAMShape

The transform sits at the parent's origin (translate / rotate 0, scale 1, locked), so it follows
the camera work of the original camera. The lens and film back are connected from the original
shape (LINKED_ATTRS); the 2D attributes that SyncBridge moves (pixel_mapping.CAMERA_ATTRS) belong
to the dedicated camera and are copied once when it is made. H-MY-30: the dedicated camera sees
exactly what the original sees until SyncBridge moves its 2D attributes.
"""
from __future__ import annotations

import re
from typing import List, Optional

from maya import cmds

from .pixel_mapping import CAMERA_ATTRS

MARK_ATTR = "syncBridgeLayer"          # on the dedicated camera's transform: the Maya layer id
LINKED_ATTRS = ("focalLength", "horizontalFilmAperture", "verticalFilmAperture", "filmFit", "filmFitOffset",
                "lensSqueezeRatio", "cameraScale", "nearClipPlane", "farClipPlane", "orthographic",
                "orthographicWidth", "fStop", "focusDistance", "depthOfField", "shutterAngle",
                "shakeEnabled", "horizontalShake", "verticalShake", "shakeOverscanEnabled", "shakeOverscan")
OWN_ATTRS = tuple(CAMERA_ATTRS.values()) + ("overscan",)   # overscan follows the gate of each view (D-27)


def node_name(layer_name: str) -> str:
    """SB_<layer>_CAM with only the characters Maya allows in names."""
    base = re.sub(r"[^A-Za-z0-9_]", "_", layer_name or "").strip("_") or "Layer"
    return "SB_%s_CAM" % base


def _transform(shape: str) -> str:
    return cmds.listRelatives(shape, parent=True, fullPath=True)[0]


def _shape(node: str) -> str:
    if cmds.nodeType(node) == "camera":
        return cmds.ls(node, long=True)[0]
    shapes = cmds.listRelatives(node, shapes=True, type="camera", fullPath=True) or []
    if not shapes:
        raise ValueError(u"%s はカメラではありません。" % node)
    return shapes[0]


def layer_of(camera: str) -> Optional[str]:
    """The Maya layer id when `camera` (transform or shape) is a SyncBridge dedicated camera."""
    shape = _shape(camera)
    tr = _transform(shape)
    if cmds.attributeQuery(MARK_ATTR, node=tr, exists=True):
        return cmds.getAttr("%s.%s" % (tr, MARK_ATTR)) or None
    return None


def unfollowed_motion(original: str) -> List[str]:
    """2D attributes of the original camera that are keyed or connected: the dedicated camera keeps its
    own values for them, so that motion does not reach it."""
    shape = _shape(original)
    return [attr for attr in OWN_ATTRS
            if cmds.listConnections("%s.%s" % (shape, attr), source=True, destination=False)]


def _link(original_shape: str, shape: str) -> None:
    for attr in LINKED_ATTRS:
        cmds.connectAttr("%s.%s" % (original_shape, attr), "%s.%s" % (shape, attr), force=True)


def _copy_own(original_shape: str, shape: str) -> None:
    for attr in OWN_ATTRS:
        cmds.setAttr("%s.%s" % (shape, attr), cmds.getAttr("%s.%s" % (original_shape, attr)))


def create(original: str, layer_name: str, layer_id: str) -> str:
    """A dedicated camera under `original` for the Maya layer; returns its shape (full path)."""
    original_shape = _shape(original)
    if layer_of(original_shape):
        raise ValueError(u"%s は SyncBridge の専用カメラです。元のカメラを選んでください。"
                         % original_shape.split("|")[-1])
    tr = cmds.camera()[0]
    tr = cmds.parent(tr, _transform(original_shape), relative=True)[0]
    shape = _shape(_named(cmds.ls(tr, long=True)[0], layer_name))
    tr = _transform(shape)
    cmds.addAttr(tr, longName=MARK_ATTR, dataType="string")
    cmds.setAttr("%s.%s" % (tr, MARK_ATTR), layer_id, type="string")
    _place(tr)
    _copy_own(original_shape, shape)
    _link(original_shape, shape)
    return shape


PLACE_ATTRS = ["%s%s" % (a, x) for a in ("translate", "rotate", "scale", "rotateAxis") for x in "XYZ"] + \
    ["shearXY", "shearXZ", "shearYZ"]


def _place(tr: str) -> None:
    """At the parent's origin, locked (the camera work belongs to the original camera)."""
    for attr in PLACE_ATTRS:
        plug = "%s.%s" % (tr, attr)
        cmds.setAttr(plug, lock=False)
        cmds.setAttr(plug, 1.0 if attr.startswith("scale") else 0.0)
        cmds.setAttr(plug, lock=True)


def retarget(camera: str, original: str) -> str:
    """Move a dedicated camera under another original camera (the 2D values are copied again).
    Returns its shape (new full path)."""
    shape, original_shape = _shape(camera), _shape(original)
    if layer_of(original_shape):
        raise ValueError(u"%s は SyncBridge の専用カメラです。元のカメラを選んでください。"
                         % original_shape.split("|")[-1])
    tr = cmds.parent(_transform(shape), _transform(original_shape), relative=True)[0]
    tr = cmds.ls(tr, long=True)[0]
    _place(tr)
    shape = _shape(tr)
    _copy_own(original_shape, shape)
    _link(original_shape, shape)
    return shape


def _named(tr: str, layer_name: str) -> str:
    """Name the transform SB_<layer>_CAM and its shape SB_<layer>_CAMShape (Maya adds a number when the
    name is taken); returns the transform's full path."""
    tr = cmds.ls(cmds.rename(tr, node_name(layer_name)), long=True)[0]
    shape = cmds.listRelatives(tr, shapes=True, type="camera", fullPath=True)[0]
    cmds.rename(shape, tr.split("|")[-1] + "Shape")
    return tr


def rename(camera: str, layer_name: str) -> str:
    """Rename the dedicated camera after its layer; returns the shape's new full path."""
    return _shape(_named(_transform(_shape(camera)), layer_name))


def delete(camera: str) -> None:
    cmds.delete(_transform(_shape(camera)))
