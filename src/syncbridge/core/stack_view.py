"""The SyncBridge viewer's margin (D-34): the stacked view zoomed out a little, so the area around the
comp frame shows, without touching any camera's overscan (that would reach playblasts, H-PM-9).

Each layer is drawn with a projection made here from the camera model that the renders confirmed
(core.pixel_mapping.project: film offset, pan / zoom, pre / post scale, film roll, film translate),
with the view's size as the "render" and the picture shrunk by `margin`. The model maps camera space
(x / -z, y / -z) to the view by a 2D affine map, so the projection is a 4x4 matrix whose depth and w
columns are the ones Maya uses (copied from the view). The comp frame goes through the same map.

    affine = ndc_affine(camera, view_w, view_h, margin)       (x/-z, y/-z) -> NDC
    matrix = projection_rows(affine, depth_columns)            16 numbers for MCameraOverride
Pure functions, standard library only. Perspective cameras only.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from .pixel_mapping import project

Affine = Tuple[float, float, float, float, float, float]     # x' = a*u + b*v + c,  y' = d*u + e*v + f


def view_camera(camera: dict, margin: float = 1.0) -> dict:
    """The camera as a view draws it: pan / zoom when enabled (whatever renderPanZoom says), the
    overscan shrinks the picture, times `margin`."""
    out = dict(camera)
    out["render_pan_zoom"] = bool(camera.get("pan_zoom_enabled"))
    out["view_overscan"] = True
    out["overscan"] = float(camera.get("overscan", 1.0) or 1.0) * float(margin)
    return out


def ndc_affine(camera: dict, view_w: float, view_h: float, margin: float = 1.0) -> Affine:
    """(x / -z, y / -z) in camera space -> view NDC (x right, y up, -1..1) of a perspective camera."""
    if camera.get("orthographic"):
        raise ValueError("perspective cameras only")
    cam = view_camera(camera, margin)
    view = {"width": float(view_w), "height": float(view_h), "pixel_aspect": 1.0}

    def ndc(u, v):
        px, py = project(cam, view, (u, v, -1.0))
        return 2.0 * px / view_w - 1.0, 1.0 - 2.0 * py / view_h
    ox, oy = ndc(0.0, 0.0)
    ux, uy = ndc(1.0, 0.0)
    vx, vy = ndc(0.0, 1.0)
    return (ux - ox, vx - ox, ox, uy - oy, vy - oy, oy)


def compose(outer: Affine, inner: Affine) -> Affine:
    """outer after inner (both 2D affine maps)."""
    a, b, c, d, e, f = outer
    p, q, r, s, t, u = inner
    return (a * p + b * s, a * q + b * t, a * r + b * u + c, d * p + e * s, d * q + e * t, d * r + e * u + f)


def invert(affine: Affine) -> Affine:
    a, b, c, d, e, f = affine
    det = a * e - b * d
    if abs(det) < 1e-15:
        raise ValueError("the affine map cannot be inverted")
    ia, ib, id_, ie = e / det, -b / det, -d / det, a / det
    return (ia, ib, -(ia * c + ib * f), id_, ie, -(id_ * c + ie * f))


def map_point(affine: Affine, point: Sequence[float]) -> Tuple[float, float]:
    """A 2D point through an affine map."""
    a, b, c, d, e, f = affine
    return a * point[0] + b * point[1] + c, d * point[0] + e * point[1] + f


# -- the viewer's 2D pan / zoom (D-44) -------------------------------------------------------------------
# The editing layer is looked at through a viewer camera: the layer's dedicated camera with its own 2D pan
# folded into the film offset and its zoom into the pre-scale (fold_pan_zoom), so the viewer camera's own
# 2D pan / zoom are free for Maya's 2D Pan/Zoom tool. What that adds is `view_affine`: NDC of the editing
# layer's camera -> NDC of the view. The other layers and the comp frame go through it too.
def fold_pan_zoom(camera: dict) -> dict:
    """The camera with its 2D pan / zoom moved into film offset / pre-scale and the 2D pan / zoom reset:
    the same picture (pan acts on the film like the offset, zoom divides like the pre-scale)."""
    out = dict(camera)
    if camera.get("pan_zoom_enabled"):
        out["hfo"] = float(camera.get("hfo", 0.0)) + float(camera.get("hpan", 0.0))
        out["vfo"] = float(camera.get("vfo", 0.0)) + float(camera.get("vpan", 0.0))
        out["pre_scale"] = float(camera.get("pre_scale", 1.0)) / float(camera.get("zoom", 1.0) or 1.0)
    out.update(hpan=0.0, vpan=0.0, zoom=1.0, pan_zoom_enabled=False)
    return out


def with_view(camera: dict, hpan: float, vpan: float, zoom: float) -> dict:
    """The viewer camera: `camera` folded, then the view's 2D pan / zoom."""
    out = fold_pan_zoom(camera)
    out.update(hpan=float(hpan), vpan=float(vpan), zoom=float(zoom), pan_zoom_enabled=True)
    return out


def view_affine(editing: dict, viewer: dict, view_w: float, view_h: float) -> Affine:
    """NDC as the editing layer's camera draws -> NDC as the viewer camera draws (overscan 1 both)."""
    return compose(ndc_affine(viewer, view_w, view_h), invert(ndc_affine(editing, view_w, view_h)))


def match_view(view: Affine, camera: dict, view_w: float, view_h: float) -> Tuple[float, float, float]:
    """(hpan, vpan, zoom) of the viewer camera that gives the view `view` (a view_affine) when `camera`
    is the editing layer's camera. The same numbers act differently through another camera's film back,
    film translate and scales, and the view moved a little when the editing layer changed (the user,
    2026-10-27). The zoom scales the view (1 / zoom), the pan moves it linearly."""
    def affine(hpan, vpan, zoom):
        return view_affine(camera, with_view(camera, hpan, vpan, zoom), view_w, view_h)

    def scale(a):
        return math.sqrt(abs(a[0] * a[4] - a[1] * a[3]))
    zoom = scale(affine(0.0, 0.0, 1.0)) / scale(view)
    base, along_h, along_v = affine(0.0, 0.0, zoom), affine(1.0, 0.0, zoom), affine(0.0, 1.0, zoom)
    a, b = along_h[2] - base[2], along_v[2] - base[2]
    d, e = along_h[5] - base[5], along_v[5] - base[5]
    det = a * e - b * d
    if abs(det) < 1e-15:
        raise ValueError("the 2D pan does not move this camera's picture")
    dx, dy = view[2] - base[2], view[5] - base[5]
    return (dx * e - b * dy) / det, (a * dy - d * dx) / det, zoom


def pixel_to_ndc(x: float, y: float, view_w: float, view_h: float) -> Tuple[float, float]:
    """A point of the view widget (Qt pixels, y down) -> NDC (y up)."""
    return 2.0 * x / view_w - 1.0, 1.0 - 2.0 * y / view_h


def ray_direction(layer_affine: Affine, ndc: Sequence[float]) -> Tuple[float, float, float]:
    """Camera-space direction (u, v, -1) of the ray through a view point, for a layer drawn with
    `layer_affine` ((x/-z, y/-z) -> view NDC)."""
    u, v = map_point(invert(layer_affine), ndc)
    return u, v, -1.0


def ndc_to_pixel(ndc: Sequence[float], view_w: float, view_h: float) -> Tuple[float, float]:
    """NDC (y up) -> a point of the view widget (Qt pixels, y down); the inverse of pixel_to_ndc."""
    return (ndc[0] + 1.0) * 0.5 * view_w, (1.0 - ndc[1]) * 0.5 * view_h


def polyline_distance(point: Sequence[float], points: Sequence[Sequence[float]]) -> float:
    """Shortest 2D distance from `point` to the polyline through `points` (a curve drawn in the view,
    P-7: a click near a NURBS curve picks it). Infinite without points."""
    px, py = point
    best = math.inf
    for i, (ax, ay) in enumerate(points):
        bx, by = points[i + 1] if i + 1 < len(points) else (ax, ay)
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0.0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
        best = min(best, math.hypot(px - (ax + t * dx), py - (ay + t * dy)))
    return best


def apply_affine(affine: Affine, point: Sequence[float]) -> Tuple[float, float]:
    """NDC of a camera-space point."""
    x, y, z = point
    u, v = x / -z, y / -z
    a, b, c, d, e, f = affine
    return a * u + b * v + c, d * u + e * v + f


def to_pixels(ndc: Tuple[float, float], viewport: Sequence[float]) -> Tuple[float, float]:
    """View pixels (2D drawing: origin bottom-left) of an NDC point; viewport = (x0, y0, width, height)."""
    x0, y0, w, h = viewport
    return x0 + (ndc[0] + 1.0) * 0.5 * w, y0 + (ndc[1] + 1.0) * 0.5 * h


def projection_rows(affine: Affine, depth: Optional[Sequence[Sequence[float]]] = None,
                    near: float = 0.1, far: float = 10000.0) -> List[float]:
    """4x4 projection for row vectors (clip = p * M), row-major, from the affine map and the depth / w
    columns of the view's own projection (rows 0..3 of columns 2 and 3); OpenGL's when not given.
    x and y follow w: x_clip / w is the affine map whatever sign Maya gives w."""
    if depth is None:
        depth = [(0.0, 0.0), (0.0, 0.0), (-(far + near) / (far - near), -1.0), (-2.0 * far * near / (far - near), 0.0)]
    c = float(depth[2][1])                     # w = c * z (c = -1 in OpenGL)
    if abs(c) < 1e-12 or abs(float(depth[3][1])) > 1e-9 or abs(float(depth[0][1])) > 1e-9 \
            or abs(float(depth[1][1])) > 1e-9:
        raise ValueError("not a perspective projection")
    a, b, cc, d, e, f = affine
    s = -c
    return [s * a, s * d, float(depth[0][0]), float(depth[0][1]),
            s * b, s * e, float(depth[1][0]), float(depth[1][1]),
            -s * cc, -s * f, float(depth[2][0]), float(depth[2][1]),
            0.0, 0.0, float(depth[3][0]), float(depth[3][1])]
