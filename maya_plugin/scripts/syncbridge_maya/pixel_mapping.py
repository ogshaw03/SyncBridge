"""Pixel Mapping, Maya side (docs/PIXEL_MAPPING.md): read the camera and the BG plane, apply the
offsets that syncbridge.core.pixel_mapping solves.

    cam = camera_data("BG_CAMShape")
    bg = bg_plane_data("bgPlane", 6000, 4000)       # source size of the BG image in pixels
    result = pixel_mapping.solve("film_offset", cam, render_data(), bg, ae_matrix, comp)
    apply_values("BG_CAMShape", result["values"])    # one undo; refuses keyed / connected attributes

The camera's transform and the rig are never changed (spec 16-6, 16-7).
"""
from __future__ import annotations

from typing import Dict, List

from maya import cmds

CAMERA_ATTRS = {
    "hfo": "horizontalFilmOffset", "vfo": "verticalFilmOffset",
    "ft_h": "filmTranslateH", "ft_v": "filmTranslateV",
    "pan_zoom_enabled": "panZoomEnabled", "render_pan_zoom": "renderPanZoom",
    "hpan": "horizontalPan", "vpan": "verticalPan", "zoom": "zoom",
}


def _shape(camera: str) -> str:
    if cmds.nodeType(camera) == "camera":
        return camera
    shapes = cmds.listRelatives(camera, shapes=True, type="camera", fullPath=True) or []
    if not shapes:
        raise ValueError(u"%s はカメラではありません。" % camera)
    return shapes[0]


def camera_data(camera: str) -> dict:
    shape = _shape(camera)

    def get(attr):
        return cmds.getAttr("%s.%s" % (shape, attr))
    data = {
        "name": shape,
        "orthographic": bool(get("orthographic")),
        "focal_length": get("focalLength"),
        "hfa": get("horizontalFilmAperture"),
        "vfa": get("verticalFilmAperture"),
        "film_fit": get("filmFit"),
        "ortho_width": get("orthographicWidth"),
        "lens_squeeze": get("lensSqueezeRatio"),
        "camera_scale": get("cameraScale"),
        "film_roll": get("filmRollValue"),
        "pre_scale": get("preScale"),
        "post_scale": get("postScale"),
        "film_fit_offset": get("filmFitOffset"),
        "overscan": get("overscan"),
        "world_inverse": list(cmds.getAttr(shape + ".worldInverseMatrix[0]")),
    }
    for key, attr in CAMERA_ATTRS.items():
        data[key] = get(attr)
    return data


def render_data() -> dict:
    return {"width": cmds.getAttr("defaultResolution.width"), "height": cmds.getAttr("defaultResolution.height"),
            "pixel_aspect": cmds.getAttr("defaultResolution.pixelAspect")}


def bg_plane_data(mesh: str, width: float, height: float) -> dict:
    """World positions of the BG image's corners on a mesh, from its UVs (v = 0 is the image bottom).

    Points are taken inside the UV square and extended linearly to the corners, so the mesh may have
    any number of faces; a bent mesh gives a non-affine result that the core refuses."""
    import maya.api.OpenMaya as om
    sel = om.MSelectionList()
    sel.add(mesh)
    path = sel.getDagPath(0)
    path.extendToShape()
    fn = om.MFnMesh(path)

    def at_uv(u, v):
        for face in range(fn.numPolygons):
            try:
                p = fn.getPointAtUV(face, u, v, om.MSpace.kWorld, tolerance=1e-6)
                return (p.x, p.y, p.z)
            except RuntimeError:
                continue
        raise ValueError(u"%s の UV (%g, %g) に面がありません（BG の画像全体が UV 0〜1 に入っている板ポリを選んでください）。"
                         % (mesh, u, v))
    a, b, c = at_uv(0.25, 0.75), at_uv(0.75, 0.75), at_uv(0.25, 0.25)
    du = [(b[i] - a[i]) * 2.0 for i in range(3)]          # u 0 -> 1
    dv = [(a[i] - c[i]) * 2.0 for i in range(3)]          # v 0 -> 1 (image bottom -> top)
    top_left = tuple(a[i] - 0.25 * du[i] + 0.25 * dv[i] for i in range(3))
    return {"mesh": mesh, "width": float(width), "height": float(height), "top_left": top_left,
            "top_right": tuple(top_left[i] + du[i] for i in range(3)),
            "bottom_left": tuple(top_left[i] - dv[i] for i in range(3))}


def conflicts(camera: str, keys: List[str]) -> List[str]:
    """Attributes that SyncBridge must not overwrite: keyed, connected or locked."""
    shape = _shape(camera)
    out = []
    for key in keys:
        plug = "%s.%s" % (shape, CAMERA_ATTRS[key])
        if cmds.getAttr(plug, lock=True):
            out.append(u"%s はロックされています" % plug)
        elif cmds.listConnections(plug, source=True, destination=False):
            out.append(u"%s にキーか接続があります" % plug)
    return out


def apply_values(camera: str, values: Dict[str, object]) -> dict:
    """Set the solved values in one undo chunk; returns the previous values (the backup)."""
    shape = _shape(camera)
    problems = conflicts(camera, list(values))
    if problems:
        raise ValueError(u"カメラを変更していません: " + "、".join(problems))
    before = {key: cmds.getAttr("%s.%s" % (shape, CAMERA_ATTRS[key])) for key in values}
    cmds.undoInfo(openChunk=True, chunkName="SyncBridge pixel mapping")
    try:
        for key, value in values.items():
            cmds.setAttr("%s.%s" % (shape, CAMERA_ATTRS[key]), value)
    finally:
        cmds.undoInfo(closeChunk=True)
    return before
