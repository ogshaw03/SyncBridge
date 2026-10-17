"""AE comp resolution frame shown in a Maya view (comp guide, D-16).

Maya often renders with a margin (e.g. 2112x1188) and AE crops it to the final comp size
(e.g. 1920x1080). The guide draws the comp's area inside Maya's resolution gate so the
layout can be checked in the viewport.

Assumptions (agreed with the user, 2026-10-16): the Maya render is placed in the comp at
its centre and at 100% (one render pixel = one comp pixel). Only the comp's width and
height are used.

Pure functions, standard library only; used by the Maya plug-in (drawing) and the Maya
adapter (warnings). Maya's resolution-gate fit is H-MY-20 (not yet compared in Maya).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

INCH_MM = 25.4

# camera.filmFit enum (H-MY-20)
FIT_FILL, FIT_HORIZONTAL, FIT_VERTICAL, FIT_OVERSCAN = 0, 1, 2, 3


def parse_comp(data) -> Dict[str, object]:
    """Validate the comp description sent by AE: {name, width, height, pixelAspect?}."""
    if not isinstance(data, dict):
        raise ValueError("comp must be an object")
    try:
        width, height = int(data["width"]), int(data["height"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("comp needs integer width and height")
    if width <= 0 or height <= 0:
        raise ValueError("comp size must be positive (got %dx%d)" % (width, height))
    try:
        pixel_aspect = float(data.get("pixelAspect", 1.0) or 1.0)
    except (TypeError, ValueError):
        raise ValueError("pixelAspect must be a number")
    return {"name": str(data.get("name") or ""), "width": width, "height": height,
            "pixel_aspect": pixel_aspect}


def frame_fraction(render_w: int, render_h: int, comp_w: int, comp_h: int) -> Tuple[float, float]:
    """Comp size as a fraction of the render size (1.0 = the whole resolution gate)."""
    if render_w <= 0 or render_h <= 0:
        raise ValueError("render resolution must be positive (got %sx%s)" % (render_w, render_h))
    return comp_w / float(render_w), comp_h / float(render_h)


def resolution_gate(film_fit: int, h_aperture_in: float, v_aperture_in: float,
                    device_aspect: float) -> Tuple[float, float]:
    """Size of the resolution gate on the film back, in millimetres (H-MY-20).

    fill       : the resolution gate fits inside the film gate
    horizontal : same width as the film gate
    vertical   : same height as the film gate
    overscan   : the film gate fits inside the resolution gate
    """
    film_w, film_h = h_aperture_in * INCH_MM, v_aperture_in * INCH_MM
    if film_w <= 0 or film_h <= 0 or device_aspect <= 0:
        raise ValueError("film aperture and device aspect must be positive")
    film_aspect = film_w / film_h
    if film_fit == FIT_FILL:
        fit = FIT_HORIZONTAL if device_aspect > film_aspect else FIT_VERTICAL
    elif film_fit == FIT_OVERSCAN:
        fit = FIT_VERTICAL if device_aspect > film_aspect else FIT_HORIZONTAL
    else:
        fit = film_fit
    if fit == FIT_HORIZONTAL:
        return film_w, film_w / device_aspect
    if fit == FIT_VERTICAL:
        return film_h * device_aspect, film_h
    raise ValueError("unknown filmFit %r" % film_fit)


def guide_rect(camera: dict, render: dict, comp: dict, distance: float) -> Dict[str, object]:
    """Corners of the comp frame in camera space (camera looks down -Z) at `distance`.

    camera: {orthographic, orthographic_width, focal_length (mm), h_aperture, v_aperture (in),
             h_offset, v_offset (in), film_fit}
    render: {width, height, device_aspect}
    comp  : parse_comp() result
    Returns {corners: [(x, y, z) x4, counter-clockwise from bottom-left], gate: (half_w, half_h),
             fraction: (fx, fy)}.
    """
    fx, fy = frame_fraction(render["width"], render["height"], comp["width"], comp["height"])
    device_aspect = render.get("device_aspect") or render["width"] / float(render["height"])
    if camera.get("orthographic"):
        # Orthographic: the gate is orthographicWidth wide along the fitted axis (H-MY-20).
        width = float(camera["orthographic_width"])
        gate_w, gate_h = resolution_gate(camera.get("film_fit", FIT_FILL), camera["h_aperture"],
                                         camera["v_aperture"], device_aspect)
        film_w = camera["h_aperture"] * INCH_MM
        scale = width / film_w
        half_w, half_h = gate_w * scale / 2.0, gate_h * scale / 2.0
        off_x = camera.get("h_offset", 0.0) * INCH_MM * scale
        off_y = camera.get("v_offset", 0.0) * INCH_MM * scale
    else:
        focal = float(camera["focal_length"])
        if focal <= 0:
            raise ValueError("focal length must be positive")
        gate_w, gate_h = resolution_gate(camera.get("film_fit", FIT_FILL), camera["h_aperture"],
                                         camera["v_aperture"], device_aspect)
        k = distance / focal
        half_w, half_h = gate_w / 2.0 * k, gate_h / 2.0 * k
        off_x = camera.get("h_offset", 0.0) * INCH_MM * k
        off_y = camera.get("v_offset", 0.0) * INCH_MM * k
    w, h, z = half_w * fx, half_h * fy, -distance
    corners = [(off_x - w, off_y - h, z), (off_x + w, off_y - h, z),
               (off_x + w, off_y + h, z), (off_x - w, off_y + h, z)]
    return {"corners": corners, "gate": (half_w, half_h), "fraction": (fx, fy)}


def draw_distance(near_clip: float, far_clip: float) -> float:
    """A depth between the clip planes to draw at (the frame looks the same at any depth)."""
    near = max(float(near_clip), 1e-4)
    far = float(far_clip)
    d = near * 2.0
    if far > near and d >= far:
        d = (near + far) / 2.0
    return d


def warnings(camera: dict, render: dict, comp: dict) -> List[str]:
    """What the guide cannot show correctly, in Japanese for the panels."""
    out = []
    if comp["width"] > render["width"] or comp["height"] > render["height"]:
        out.append(u"枠（%dx%d）が Maya のレンダー解像度（%dx%d）より大きいため、解像度ゲートの外にはみ出します。"
                   % (comp["width"], comp["height"], render["width"], render["height"]))
    maya_pa = float(render.get("pixel_aspect", 1.0) or 1.0)
    if abs(maya_pa - comp["pixel_aspect"]) > 1e-3:
        out.append(u"ピクセル縦横比が違います（Maya %.3f、枠 %.3f）。枠はピクセル数の比で描いています。"
                   % (maya_pa, comp["pixel_aspect"]))
    ignored = []
    for key, label, default in (("lens_squeeze", "Lens Squeeze Ratio", 1.0), ("camera_scale", "Camera Scale", 1.0),
                                ("pre_scale", "Pre Scale", 1.0), ("post_scale", "Post Scale", 1.0)):
        value = camera.get(key)
        if value is not None and abs(float(value) - default) > 1e-6:
            ignored.append("%s=%g" % (label, value))
    for key, label in (("film_translate_h", "Film Translate H"), ("film_translate_v", "Film Translate V")):
        value = camera.get(key)
        if value:
            ignored.append("%s=%g" % (label, value))
    if ignored:
        out.append(u"カメラの次の設定は枠に反映していません: %s" % ", ".join(ignored))
    return out


def label(comp: dict, render: Optional[dict] = None) -> str:
    """'AE main 1920x1080 / Maya 2112x1188' (the name says where the size came from; a size
    typed in the Maya panel has no name: '1920x1080 / Maya 2112x1188')."""
    text = "%dx%d" % (comp["width"], comp["height"])
    if comp["name"]:
        text = "%s %s" % (comp["name"], text)
    if render:
        text += " / Maya %dx%d" % (render["width"], render["height"])
    return text
