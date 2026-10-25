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
    "pre_scale": "preScale", "post_scale": "postScale", "film_roll": "filmRollValue",
    "roll_pivot_h": "horizontalRollPivot", "roll_pivot_v": "verticalRollPivot", "film_roll_order": "filmRollOrder",
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


def apply_values(camera: str, values: Dict[str, object], also=None) -> dict:
    """Set the solved values in one undo chunk (with `also()`, e.g. saving the mapping, inside the same
    chunk); returns the previous values (the backup)."""
    shape = _shape(camera)
    problems = conflicts(camera, list(values))
    if problems:
        raise ValueError(u"カメラを変更していません: " + "、".join(problems))
    before = {key: cmds.getAttr("%s.%s" % (shape, CAMERA_ATTRS[key])) for key in values}
    cmds.undoInfo(openChunk=True, chunkName="SyncBridge pixel mapping")
    try:
        for key, value in values.items():
            cmds.setAttr("%s.%s" % (shape, CAMERA_ATTRS[key]), value)
        if also is not None:
            also()
    finally:
        cmds.undoInfo(closeChunk=True)
    return before


METHOD_LABELS = {"film_offset": "Film Offset", "film_translate": "Film Translate", "pan_zoom": "2D Pan/Zoom",
                 "film_roll": u"Film Translate・Scale・Roll"}


def _ae_layer(info: dict) -> dict:
    comp, layer = info["comp"], info["layer"]
    return {"comp_id": comp.get("id"), "comp": comp.get("name"), "layer_id": layer.get("id"),
            "layer": layer.get("name"), "source": layer.get("source"),
            "source_width": layer["source_width"], "source_height": layer["source_height"]}


def _backup(mapping: dict, camera: str, before: dict) -> str:
    import datetime
    import json
    import os
    from .exchange import backup_dir
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")     # two sends in one second must not collide
    path = os.path.join(backup_dir(), "pixelmap_%s.json" % stamp)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"syncbridge": "pixel mapping camera backup", "scene": cmds.file(q=True, sn=True),
                   "camera": camera, "mapping": mapping, "before": before}, f, indent=2, ensure_ascii=False)
    return path


REFERENCE_KEYS = {"film_offset": ("hfo", "vfo"), "film_translate": ("ft_h", "ft_v"),
                  "pan_zoom": ("hpan", "vpan", "zoom", "pan_zoom_enabled", "render_pan_zoom"),
                  "film_roll": ("ft_h", "ft_v", "post_scale", "film_roll")}


def apply_from_ae(info: dict, options: dict = None, confirm: bool = True) -> dict:
    """pixelmap.apply.request: put the AE BG layer's position on the mapped camera (D-24, D-25).

    The virtual layer for the AE layer is found in the scene; when there is none, it is made from the
    camera / BG / method / mode chosen in the SyncBridge panel, after the user confirms.
      absolute mode: the BG plane in the scene gives the camera values (core.pixel_mapping.solve).
      relative mode: the first send records the reference (AE layer now, camera values now) and changes
                     nothing; later sends add the AE layer's 2D change since the reference
                     (core.pixel_mapping.solve_relative). No BG geometry needed.
    Returns {status: applied | unchanged | cancelled, mapping, values, before, max_error_px, warnings, ...}."""
    from syncbridge.core import layer_mapping as core_lm
    from syncbridge.core import pixel_mapping as core_pm
    from . import layer_mapping
    options = options or {}
    ae = _ae_layer(info)
    mappings = layer_mapping.stored()
    mapping = core_lm.find(mappings, ae)
    created = mapping is None
    if created:
        chosen = layer_mapping.defaults()
        mode = options.get("mode") or chosen["mode"]
        if not chosen["camera"] or (mode == "absolute" and not chosen["bg"]):
            raise ValueError(u"AE のレイヤー「%s」はまだ Maya のカメラに対応付けられていません。Maya の SyncBridge パネルの"
                             u"「Pixel Mapping」欄で、カメラ%sを選んでから、もう一度送ってください。"
                             % (ae["layer"], u"と BG" if mode == "absolute" else u""))
        maya = {"camera_uuid": layer_mapping.uuid_of(chosen["camera"]), "camera": chosen["camera"]}
        if mode == "absolute":
            maya.update(bg_uuid=layer_mapping.uuid_of(chosen["bg"]), bg=chosen["bg"])
        mapping = core_lm.new_mapping(ae, maya, options.get("method") or chosen["method"], mode=mode)
    else:
        mapping = dict(mapping, ae=dict(mapping["ae"], **{k: v for k, v in ae.items() if v is not None}),
                       maya=dict(mapping["maya"]))
    if not mapping.get("enabled", True):
        raise ValueError(u"対応付け「%s」は無効になっています。" % mapping["name"])
    mode = core_lm.mode_of(mapping)
    camera = layer_mapping.node_by_uuid(mapping["maya"]["camera_uuid"])
    if camera is None:
        raise ValueError(u"対応付け「%s」のカメラ（%s）がシーンにありません。" % (mapping["name"], mapping["maya"].get("camera")))
    mapping["maya"]["camera"] = camera
    bg_node = None
    if mode == "absolute":
        bg_node = layer_mapping.node_by_uuid(mapping["maya"].get("bg_uuid"))
        if bg_node is None:
            raise ValueError(u"対応付け「%s」の BG（%s）がシーンにありません。" % (mapping["name"], mapping["maya"].get("bg")))
        mapping["maya"]["bg"] = bg_node

    transform, warnings = core_lm.ae_layer_from_export(info)
    matrix, more = core_pm.ae_layer_matrix(transform)
    warnings += more
    for other in core_lm.camera_conflicts(mappings, mapping):
        warnings.append(u"カメラ %s は対応付け「%s」でも同じ方式で動かしています。最後に送った位置になります。"
                        % (camera.split("|")[-1], other["name"]))
    comp = {"width": info["comp"]["width"], "height": info["comp"]["height"],
            "pixelAspect": info["comp"].get("pixelAspect", 1.0)}
    cam = camera_data(camera)
    # overscan: the AE footage is a playblast (shows the overscan margin) or a render (does not), H-PM-9
    cam["view_overscan"] = layer_mapping.defaults()["view_overscan"]
    method = mapping["method"]

    if created and confirm:
        from . import dialogs
        what = (u"今の見え方を基準として記録しますか？（カメラは変えません。次から AE の BG の動きを %s に足します）"
                % METHOD_LABELS.get(method, method)) if mode == "relative" else \
            (u"BG「%s」に合わせて %s を設定しますか？" % (bg_node.split("|")[-1], METHOD_LABELS.get(method, method)))
        text = (u"AE のレイヤー「%s」（コンプ「%s」）を、Maya のカメラ「%s」に対応付けて、%s\n\n"
                u"対応付けはこのシーンに保存され、次からは確認なしで設定します。元に戻すときは Ctrl+Z を 1 回。"
                % (ae["layer"], ae["comp"], camera.split("|")[-1], what))
        if not dialogs.ask("SyncBridge", text, u"対応付ける", u"キャンセル"):
            return {"status": "cancelled"}

    base = {"status": "applied", "created": created, "camera": camera, "frame": cmds.currentTime(q=True),
            "mode": mode}
    if mode == "relative" and not mapping.get("reference"):
        values_now = {k: cam[k] for k in REFERENCE_KEYS[method]}
        mapping = core_lm.with_reference(mapping, matrix, values_now, info["comp"].get("time"))
        updated = core_lm.upsert(mappings, mapping)
        cmds.undoInfo(openChunk=True, chunkName="SyncBridge pixel mapping reference")
        try:
            layer_mapping.save(updated)
        finally:
            cmds.undoInfo(closeChunk=True)
        return dict(base, status="unchanged", reference_recorded=True, values={}, before={}, shift_px=[0.0, 0.0],
                    max_error_px=0.0, warnings=warnings,
                    mapping={"id": mapping["id"], "name": mapping["name"], "text": core_lm.describe(mapping)})

    if mode == "relative":
        ref = mapping["reference"]
        solved = core_pm.solve_relative(method, dict(cam, **ref["camera"]), render_data(), comp, ref["matrix"], matrix)
        shift = [solved["change"]["dx"], solved["change"]["dy"]]
    else:
        solved = core_pm.solve(method, cam, render_data(),
                               bg_plane_data(bg_node, ae["source_width"], ae["source_height"]), matrix, comp)
        shift = solved["shift_px"]
    warnings += solved.get("warnings") or []
    updated = core_lm.upsert(mappings, mapping)
    before = apply_values(camera, solved["values"], also=lambda: layer_mapping.save(updated))
    backup = _backup(mapping, camera, before)
    return dict(base, mapping={"id": mapping["id"], "name": mapping["name"], "text": core_lm.describe(mapping)},
                values=solved["values"], before=before, shift_px=shift, max_error_px=solved["max_error_px"],
                change=solved.get("change"), warnings=warnings, backup=backup)
