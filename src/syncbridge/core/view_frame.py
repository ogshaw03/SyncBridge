"""Where the comp frame sits in the SyncBridge viewer (D-34): from the camera's film back, Film Fit and
overscan and the render's aspect only.

Film offset, pan / zoom, film translate, scale and roll move the picture, not the frame: the frame is
the comp (render) area of the view, and the layers' own 2D values move what is inside it. The
viewer first drew the frame with the view's projection, which holds the original camera's film
translate, and the frame moved with it (the user, 2026-10-25).

A view shows the camera's film fitted to the view by the Film Fit, times its overscan; the render area
is the render's aspect fitted to the film by the same Film Fit (checked against Maya's
MFnCamera.getViewingFrustum / getRenderingFrustum, H-MY-36). A comp smaller than the render sits at
its fraction in the middle (core.comp_guide). Pure functions, standard library only.

    left, bottom, right, top = frame_rect(viewport, camera, render, comp)   view pixels, origin bottom-left
"""
from __future__ import annotations

from typing import Sequence, Tuple

FILL, HORIZONTAL, VERTICAL, OVERSCAN = 0, 1, 2, 3


def _fitted(width: float, height: float, aspect: float, fit: int) -> Tuple[float, float]:
    """(w, h) of a window of `aspect` fitted to a film of width x height by Maya's Film Fit."""
    film_aspect = width / height
    if fit == FILL:
        fit = HORIZONTAL if aspect > film_aspect else VERTICAL
    elif fit == OVERSCAN:
        fit = VERTICAL if aspect > film_aspect else HORIZONTAL
    if fit == HORIZONTAL:
        return width, width / aspect
    return height * aspect, height


def frame_rect(viewport: Sequence[float], camera: dict, render: dict, comp: dict = None
               ) -> Tuple[float, float, float, float]:
    """(left, bottom, right, top) of the comp frame in view pixels; viewport = (x0, y0, width, height).
    camera = {hfa, vfa (inches), film_fit, overscan, lens_squeeze}; render = {width, height,
    pixel_aspect}; comp = {width, height} (the render's own size when None)."""
    x0, y0, view_w, view_h = (float(v) for v in viewport)
    hfa = float(camera["hfa"]) * float(camera.get("lens_squeeze", 1.0) or 1.0)
    vfa = float(camera["vfa"])
    fit = int(camera.get("film_fit", FILL))
    render_aspect = float(render["width"]) * float(render.get("pixel_aspect", 1.0)) / float(render["height"])
    vw, vh = _fitted(hfa, vfa, view_w / view_h, fit)
    overscan = float(camera.get("overscan", 1.0) or 1.0)
    rw, rh = _fitted(hfa, vfa, render_aspect, fit)
    fx = float(comp["width"]) / float(render["width"]) if comp else 1.0
    fy = float(comp["height"]) / float(render["height"]) if comp else 1.0
    half_w = view_w * rw / (vw * overscan) / 2.0 * fx
    half_h = view_h * rh / (vh * overscan) / 2.0 * fy
    cx, cy = x0 + view_w / 2.0, y0 + view_h / 2.0
    return cx - half_w, cy - half_h, cx + half_w, cy + half_h
