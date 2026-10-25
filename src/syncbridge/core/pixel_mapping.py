"""Pixel Mapping core: AE BG layer <-> Maya camera, in source pixel coordinates (docs/PIXEL_MAPPING.md).

Pure functions, standard library only, double precision, no rounding. Coordinate systems:

    Source Pixel Space   origin at the top-left corner of the source image, x right, y down, pixel
                         (i, j) covers [i, i+1) x [j, j+1). Same convention for AE layer space.
    Comp / Render Pixel  the same convention on the AE comp and on the Maya render image.
    Film (inches)        Maya film back: x right, y up, origin at the film center.
    NDC                  film / (effective film width / 2): x in [-1, 1] across the render width;
                         y uses the same unit (square pixels), up.

Maya camera model, checked by rendering in mayapy 2024 (Hardware 2.0 and Maya Software), plane
parallel to the film, horizontal film fit (H-PM-1..4):
    perspective:  film = (X / -Z, Y / -Z) * focalLength / 25.4
    orthographic: film = (X, Y) * effective width / orthographicWidth
    film offset (inches, perspective only) and 2D pan (inches, render pan/zoom on, perspective only)
    are subtracted on the film; film translate (NDC) is subtracted in NDC; zoom divides around the
    image center. Orthographic cameras ignore film offset and 2D pan in renders.
    x_px = W/2 + xn * W/2,  y_px = H/2 - yn * W/2
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

Matrix = List[List[float]]          # 3 x 3, column vectors: [x', y', 1] = M [x, y, 1]

METHODS = ("film_offset", "film_translate", "pan_zoom")
FIT_NAMES = {0: "fill", 1: "horizontal", 2: "vertical", 3: "overscan"}
AFFINE_TOLERANCE = 1e-4      # px: deviation from an affine map (plane not parallel to the film)
ERROR_LIMIT_PX = 1.0         # refuse when a size / angle difference leaves this error in the frame (spec 10)
WARN_PX = 0.1                # warn above this


# -- 2D affine helpers ---------------------------------------------------------------------------
def identity() -> Matrix:
    return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def translation(tx: float, ty: float) -> Matrix:
    return [[1.0, 0.0, float(tx)], [0.0, 1.0, float(ty)], [0.0, 0.0, 1.0]]


def scaling(sx: float, sy: float) -> Matrix:
    return [[float(sx), 0.0, 0.0], [0.0, float(sy), 0.0], [0.0, 0.0, 1.0]]


def rotation(degrees: float) -> Matrix:
    """Clockwise on screen for positive degrees in y-down pixel space (AE's rotation)."""
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]


def multiply(*ms: Matrix) -> Matrix:
    out = identity()
    for m in ms:
        out = [[sum(out[i][k] * m[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return out


def apply(m: Matrix, x: float, y: float) -> Tuple[float, float]:
    return (m[0][0] * x + m[0][1] * y + m[0][2], m[1][0] * x + m[1][1] * y + m[1][2])


def invert(m: Matrix) -> Matrix:
    a, b, c = m[0]
    d, e, f = m[1]
    det = a * e - b * d
    if abs(det) < 1e-15:
        raise ValueError("matrix is not invertible")
    return [[e / det, -b / det, (b * f - c * e) / det], [-d / det, a / det, (c * d - a * f) / det],
            [0.0, 0.0, 1.0]]


def affine_from_points(src: Sequence[Tuple[float, float]], dst: Sequence[Tuple[float, float]]) -> Matrix:
    """The affine map taking three source points to three destination points."""
    (x0, y0), (x1, y1), (x2, y2) = src
    (u0, v0), (u1, v1), (u2, v2) = dst
    det = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
    if abs(det) < 1e-12:
        raise ValueError("points are collinear")
    a = ((u1 - u0) * (y2 - y0) - (u2 - u0) * (y1 - y0)) / det
    b = ((u2 - u0) * (x1 - x0) - (u1 - u0) * (x2 - x0)) / det
    c = ((v1 - v0) * (y2 - y0) - (v2 - v0) * (y1 - y0)) / det
    d = ((v2 - v0) * (x1 - x0) - (v1 - v0) * (x2 - x0)) / det
    return [[a, b, u0 - a * x0 - b * y0], [c, d, v0 - c * x0 - d * y0], [0.0, 0.0, 1.0]]


# -- AE layer -----------------------------------------------------------------------------------
def ae_layer_matrix(layer: dict) -> Tuple[Matrix, List[str]]:
    """Source Pixel -> Comp Pixel for a 2D AE layer at one time, and the reasons it may be wrong.

    layer: {position: [x, y(, z)], anchorPoint: [x, y(, z)], scale: [sx, sy(, sz)] (percent),
            rotation: degrees, threeD: bool, parent: name or None, source: {width, height},
            effects: [names of geometry-changing effects] (optional)}
    comp = position + R(rotation) * S(scale) * (source - anchorPoint)   (H-AE-24: AE renders a layer
    pixel's center at this comp position; checked only for position, scale 100 %, rotation 0).
    Raises ValueError for what Phase 1 cannot map at all (3D layer, parent, geometry effects)."""
    if layer.get("threeD"):
        raise ValueError(u"3D レイヤーにはまだ対応していません（2D レイヤーにしてください）。")
    if layer.get("parent"):
        raise ValueError(u"親（ペアレント）のあるレイヤーにはまだ対応していません。")
    if layer.get("effects"):
        raise ValueError(u"形を変えるエフェクト（%s）のあるレイヤーにはまだ対応していません。" % ", ".join(layer["effects"]))
    px, py = layer["position"][:2]
    ax, ay = layer["anchorPoint"][:2]
    sx, sy = (layer.get("scale") or [100.0, 100.0])[:2]
    rot = float(layer.get("rotation") or 0.0)
    warnings = []
    if abs(sx - 100.0) > 1e-9 or abs(sy - 100.0) > 1e-9:
        warnings.append(u"スケール（%g%%, %g%%）は計算に入れていますが、AE のレンダーとの一致はまだ確かめていません。" % (sx, sy))
    if abs(rot) > 1e-9:
        warnings.append(u"回転（%g°）は Maya のカメラのオフセットでは表せません。" % rot)
    m = multiply(translation(px, py), rotation(rot), scaling(sx / 100.0, sy / 100.0), translation(-ax, -ay))
    return m, warnings


# -- Maya camera ----------------------------------------------------------------------------------
def _fit(camera: dict, render: dict) -> str:
    fit = camera.get("film_fit", 1)
    fit = FIT_NAMES.get(fit, fit)
    device = float(render["width"]) / float(render["height"]) * float(render.get("pixel_aspect", 1.0))
    film = float(camera["hfa"]) / float(camera["vfa"])
    if fit == "fill":
        return "horizontal" if film <= device else "vertical"
    if fit == "overscan":
        return "vertical" if film <= device else "horizontal"
    return fit


def effective_width(camera: dict, render: dict) -> float:
    """Film width in inches that spans the render width."""
    device = float(render["width"]) / float(render["height"]) * float(render.get("pixel_aspect", 1.0))
    if _fit(camera, render) == "horizontal":
        return float(camera["hfa"])
    return float(camera["vfa"]) * device


UNSUPPORTED = (("lens_squeeze", 1.0, u"Lens Squeeze Ratio"), ("camera_scale", 1.0, u"Camera Scale"),
               ("film_roll", 0.0, u"Film Roll"), ("pre_scale", 1.0, u"Pre Scale"),
               ("post_scale", 1.0, u"Post Scale"), ("film_fit_offset", 0.0, u"Film Fit Offset"),
               ("overscan", 1.0, u"Overscan"))


def check_camera(camera: dict, render: dict) -> List[str]:
    """Reasons this camera / render cannot be mapped yet (empty when it can)."""
    problems = []
    for key, default, label in UNSUPPORTED:
        if key in camera and abs(float(camera[key]) - default) > 1e-9:
            problems.append(u"%s が既定値（%g）ではありません（%g）。" % (label, default, float(camera[key])))
    if abs(float(render.get("pixel_aspect", 1.0)) - 1.0) > 1e-9:
        problems.append(u"ピクセル縦横比が 1 ではありません（まだ対応していません）。")
    if _fit(camera, render) != "horizontal":
        problems.append(u"Film Fit が横合わせになりません（%s）。Phase 1 で確かめたのは横合わせだけです。"
                        % _fit(camera, render))
    return problems


def project(camera: dict, render: dict, point: Sequence[float]) -> Tuple[float, float]:
    """Render Pixel position of a point in camera space (x right, y up, looking down -z)."""
    w, h = float(render["width"]), float(render["height"])
    eff = effective_width(camera, render)
    x, y, z = point
    if camera.get("orthographic"):
        k = eff / float(camera["ortho_width"])
        xf, yf = x * k, y * k
    else:
        if z >= 0:
            raise ValueError("point is behind the camera")
        k = float(camera["focal_length"]) / 25.4
        xf, yf = x / -z * k, y / -z * k
        xf -= float(camera.get("hfo", 0.0))
        yf -= float(camera.get("vfo", 0.0))
    pan_zoom = camera.get("pan_zoom_enabled") and camera.get("render_pan_zoom")
    if pan_zoom and not camera.get("orthographic"):
        xf -= float(camera.get("hpan", 0.0))
        yf -= float(camera.get("vpan", 0.0))
    xn = xf / (eff / 2.0) - float(camera.get("ft_h", 0.0))
    yn = yf / (eff / 2.0) - float(camera.get("ft_v", 0.0))
    px, py = w / 2.0 + xn * w / 2.0, h / 2.0 - yn * w / 2.0
    if pan_zoom:
        zoom = float(camera.get("zoom", 1.0))
        px, py = w / 2.0 + (px - w / 2.0) / zoom, h / 2.0 + (py - h / 2.0) / zoom
    return px, py


def to_camera_space(world_inverse: Sequence[float], point: Sequence[float]) -> Tuple[float, float, float]:
    """Maya's worldInverseMatrix (16 numbers, row vectors: p' = p M) applied to a world point."""
    m = world_inverse
    x, y, z = point
    return (x * m[0] + y * m[4] + z * m[8] + m[12],
            x * m[1] + y * m[5] + z * m[9] + m[13],
            x * m[2] + y * m[6] + z * m[10] + m[14])


def source_to_world(bg: dict, sx: float, sy: float) -> Tuple[float, float, float]:
    """World position of a source pixel coordinate on the BG plane.

    bg: {width, height (source px), top_left, top_right, bottom_left: world points of the source
    image's corners}."""
    o, tr, bl = bg["top_left"], bg["top_right"], bg["bottom_left"]
    u, v = float(sx) / float(bg["width"]), float(sy) / float(bg["height"])
    return tuple(o[i] + u * (tr[i] - o[i]) + v * (bl[i] - o[i]) for i in range(3))


def maya_source_to_render(camera: dict, render: dict, bg: dict) -> Matrix:
    """Source Pixel -> Render Pixel through the Maya camera (affine; ValueError when it is not)."""
    def at(sx, sy):
        return project(camera, render, to_camera_space(camera["world_inverse"], source_to_world(bg, sx, sy)))
    w, h = float(bg["width"]), float(bg["height"])
    pts = [(0.0, 0.0), (w, 0.0), (0.0, h)]
    m = affine_from_points(pts, [at(*p) for p in pts])
    for p in ((w, h), (w / 2.0, h / 2.0), (w * 0.25, h * 0.75)):
        ex, ey = apply(m, *p)
        rx, ry = at(*p)
        if math.hypot(ex - rx, ey - ry) > AFFINE_TOLERANCE:
            raise ValueError(u"BG がカメラのフィルム面と平行ではありません（遠近で形が変わるため、"
                             u"オフセットだけでは合わせられません）。")
    return m


# -- solver -----------------------------------------------------------------------------------------
METHOD_ATTRS = {"film_offset": ("hfo", "vfo"), "film_translate": ("ft_h", "ft_v"), "pan_zoom": ("hpan", "vpan")}


def solve(method: str, camera: dict, render: dict, bg: dict, source_to_comp: Matrix,
          comp: dict) -> Dict[str, object]:
    """Camera values for `method` that show the BG in Maya where AE shows it.

    Returns {values: {attr: value}, shift_px: [dx, dy], max_error_px, base: matrix}. ValueError (Japanese)
    when it cannot: unsupported camera, comp size / pixel aspect other than the render's, a different
    BG size or rotation (offsets only move the picture), or a method the camera ignores."""
    if method not in METHODS:
        raise ValueError("method must be one of %s" % (METHODS,))
    problems = check_camera(camera, render)
    if problems:
        raise ValueError(" ".join(problems))
    if (int(comp["width"]), int(comp["height"])) != (int(render["width"]), int(render["height"])):
        raise ValueError(u"AE のコンプ（%dx%d）と Maya のレンダー解像度（%dx%d）が違います。"
                         % (comp["width"], comp["height"], render["width"], render["height"]))
    if abs(float(comp.get("pixelAspect", 1.0)) - float(render.get("pixel_aspect", 1.0))) > 1e-6:
        raise ValueError(u"AE と Maya のピクセル縦横比が違います。")
    if camera.get("orthographic") and method != "film_translate":
        raise ValueError(u"平行投影のカメラでは、Film Offset と 2D Pan はレンダーに効きません（Film Translate を使ってください）。")
    zero = dict(camera)
    hx, hy = METHOD_ATTRS[method]
    zero[hx] = zero[hy] = 0.0
    if method == "pan_zoom":
        zero["pan_zoom_enabled"] = zero["render_pan_zoom"] = True
    base = maya_source_to_render(zero, render, bg)
    # Offsets only move the picture: match the source point that AE shows at the comp center, then
    # judge a size / angle difference by the error it leaves in the frame (corners), not by a ratio
    # (a camera distance typed as 18.670 instead of 18.67092 is a 0.005 % size difference, 0.05 px).
    to_source = invert(source_to_comp)
    w_c, h_c = float(comp["width"]), float(comp["height"])
    cx, cy = apply(to_source, w_c / 2.0, h_c / 2.0)
    ax, ay = apply(source_to_comp, cx, cy)
    mx, my = apply(base, cx, cy)
    dx, dy = ax - mx, ay - my
    w = float(render["width"])
    eff = effective_width(camera, render)
    if method == "film_translate":
        vx, vy = -dx * 2.0 / w, dy * 2.0 / w
    else:
        zoom = float(camera.get("zoom", 1.0)) if method == "pan_zoom" else 1.0
        vx, vy = -dx * zoom * eff / w, dy * zoom * eff / w
    solved = dict(zero)
    solved[hx], solved[hy] = vx, vy
    result = maya_source_to_render(solved, render, bg)
    err = 0.0
    for corner in ((0.0, 0.0), (w_c, 0.0), (0.0, h_c), (w_c, h_c), (w_c / 2.0, h_c / 2.0)):
        p = apply(to_source, *corner)
        rx, ry = apply(result, *p)
        err = max(err, math.hypot(corner[0] - rx, corner[1] - ry))
    warnings = []
    if err >= ERROR_LIMIT_PX:
        ratio = math.hypot(source_to_comp[0][0], source_to_comp[1][0]) / math.hypot(base[0][0], base[1][0])
        raise ValueError(u"Maya のカメラに映る BG の大きさ・向きが AE と違い、画面の端で %.2f px ずれます"
                         u"（AE は Maya の %.5f 倍）。オフセットでは位置しか合わせられません。カメラの焦点距離・距離、"
                         u"BG の大きさを AE に合わせてください。" % (err, ratio))
    if err >= WARN_PX:
        warnings.append(u"BG の大きさ・向きが AE とわずかに違い、画面の端で %.2f px ずれます（中心は合っています）。" % err)
    values = {hx: vx, hy: vy}
    if method == "pan_zoom":
        values.update(pan_zoom_enabled=True, render_pan_zoom=True)
    return {"values": values, "shift_px": [dx, dy], "max_error_px": err, "base": base, "warnings": warnings}
