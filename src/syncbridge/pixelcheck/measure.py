"""Find the test BG's markers in a rendered image and report position errors.

Render Pixel Space: origin at the top-left corner of the image, x right, y down, pixel (i, j)
covers [i, i+1) x [j, j+1) (center i + 0.5, j + 0.5) -- the same convention as the source.

    found = find_marker(img, x, y)                 # near the expected position
    report = compare(img, expected)                # expected: [{id, x, y, corner}] in render pixels
"""
from __future__ import annotations

import math
from typing import List, Optional

from .png import Image

THRESHOLD = 150          # brightest channel above this belongs to a marker (lines are <= 110)
SEARCH = 12              # pixels around the expected position (inside the marker's 31 x 31 black clear zone)


def find_marker(img: Image, x: float, y: float, search: int = SEARCH, threshold: int = THRESHOLD) -> Optional[dict]:
    """Weighted centroid of the bright pixels near (x, y), or None. Weight = brightness above the threshold.

    The centroid of a profile symmetric about the marker's center is its center, whatever the
    threshold. A blurred marker (filtered / downscaled texture) needs a low threshold so its tails
    count; the search window must then stay inside the black clear zone."""
    THRESH = threshold
    x0, x1 = max(0, int(math.floor(x)) - search), min(img.width, int(math.floor(x)) + search + 1)
    y0, y1 = max(0, int(math.floor(y)) - search), min(img.height, int(math.floor(y)) + search + 1)
    ch = img.channels
    total = sx = sy = 0.0
    color = [0.0, 0.0, 0.0]
    for j in range(y0, y1):
        row = img.rows[j]
        for i in range(x0, x1):
            px = row[i * ch:i * ch + 3] if ch >= 3 else [row[i * ch]] * 3
            v = max(px)
            if v > THRESH:
                w = float(v - THRESH)
                total += w
                sx += w * (i + 0.5)
                sy += w * (j + 0.5)
                for c in range(3):
                    color[c] += w * px[c]
    if total <= 0:
        return None
    return {"x": sx / total, "y": sy / total, "color": [c / total for c in color], "weight": total}


def _dominant(color) -> str:
    r, g, b = color
    if r > 150 and g > 150 and b < 100:
        return "br"
    if r > 150 and g < 100 and b < 100:
        return "tl"
    if g > 150 and r < 100 and b < 100:
        return "tr"
    if b > 150 and r < 100 and g < 100:
        return "bl"
    return "white"


def compare(img: Image, expected: List[dict], margin: float = 20.0, search: int = SEARCH,
            threshold: int = THRESHOLD) -> dict:
    """Errors (found - expected) for the markers that lie fully inside the image.

    Returns {count, missing, max_dx, max_dy, max_dist, mean_dx, mean_dy, corners_ok, worst, points}."""
    points, missing, corners_ok = [], [], True
    for m in expected:
        if not (margin <= m["x"] <= img.width - margin and margin <= m["y"] <= img.height - margin):
            continue
        found = find_marker(img, m["x"], m["y"], search, threshold)
        if found is None:
            missing.append(m["id"])
            continue
        dx, dy = found["x"] - m["x"], found["y"] - m["y"]
        if m.get("corner") and _dominant(found["color"]) != m["corner"]:
            corners_ok = False
        points.append({"id": m["id"], "x": m["x"], "y": m["y"], "dx": dx, "dy": dy, "dist": math.hypot(dx, dy),
                       "corner": m.get("corner")})
    if not points:
        return {"count": 0, "missing": missing, "corners_ok": corners_ok, "points": []}
    worst = max(points, key=lambda p: p["dist"])
    return {
        "count": len(points),
        "missing": missing,
        "max_dx": max(abs(p["dx"]) for p in points),
        "max_dy": max(abs(p["dy"]) for p in points),
        "max_dist": worst["dist"],
        "mean_dx": sum(p["dx"] for p in points) / len(points),
        "mean_dy": sum(p["dy"] for p in points) / len(points),
        "corners_ok": corners_ok,
        "worst": worst,
        "points": points,
    }


def summary(report: dict) -> str:
    if not report["count"]:
        return "no markers found (missing %d)" % len(report["missing"])
    return ("%d markers, mean dx %+.3f dy %+.3f, max |dx| %.3f |dy| %.3f dist %.3f px%s%s" % (
        report["count"], report["mean_dx"], report["mean_dy"], report["max_dx"], report["max_dy"],
        report["max_dist"], "" if report["corners_ok"] else ", CORNER COLORS WRONG",
        (", missing %d" % len(report["missing"])) if report["missing"] else ""))
