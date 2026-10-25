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
