"""Test BG for Pixel Mapping: grid lines and markers at known source pixel positions.

Coordinates are continuous source pixel coordinates (docs/PIXEL_MAPPING.md, Source Pixel Space):
origin at the top-left corner of the image, x right, y down, pixel (i, j) covers [i, i+1) x [j, j+1),
so its center is (i + 0.5, j + 0.5).

    lines every 10 px (1 px wide, dim) and every 100 px (1 px wide, brighter)
    a marker every STEP px: a 9 x 9 bright square in a 31 x 31 black clear zone; its position is
    the center of the square (a half-integer). Corner markers have their own colors (TL red,
    TR green, BL blue, BR yellow) so a flipped or mirrored result is recognized.
"""
from __future__ import annotations

from typing import List

from .png import Image

BACKGROUND = (32, 32, 32)
LINE_10 = (52, 52, 52)
LINE_100 = (110, 110, 110)
CLEAR = (0, 0, 0)
WHITE = (255, 255, 255)
CORNER_COLORS = {"tl": (255, 0, 0), "tr": (0, 255, 0), "bl": (0, 0, 255), "br": (255, 255, 0)}
STEP = 250
MARKER_HALF = 4          # 9 x 9 square
CLEAR_HALF = 15          # 31 x 31 clear zone


def marker_positions(width: int, height: int, step: int = STEP) -> List[dict]:
    """[{id, x, y, corner}] with x, y the continuous source position (pixel centers)."""
    xs = list(range(step // 2, width, step))
    ys = list(range(step // 2, height, step))
    out = []
    for row, cy in enumerate(ys):
        for col, cx in enumerate(xs):
            corner = None
            if (row, col) == (0, 0):
                corner = "tl"
            elif (row, col) == (0, len(xs) - 1):
                corner = "tr"
            elif (row, col) == (len(ys) - 1, 0):
                corner = "bl"
            elif (row, col) == (len(ys) - 1, len(xs) - 1):
                corner = "br"
            out.append({"id": "m%02d_%02d" % (row, col), "x": cx + 0.5, "y": cy + 0.5,
                        "px": cx, "py": cy, "corner": corner})
    return out


def make(width: int = 6000, height: int = 4000, step: int = STEP) -> Image:
    img = Image(width, height, 3)
    for y in range(height):
        img.fill_rect(0, y, width, y + 1, LINE_100 if y % 100 == 0 else (LINE_10 if y % 10 == 0 else BACKGROUND))
    for x in range(0, width, 10):
        color = LINE_100 if x % 100 == 0 else LINE_10
        for y in range(height):
            if y % 10:                                  # keep the horizontal lines' color at crossings
                img.rows[y][x * 3:x * 3 + 3] = bytes(color)
    for m in marker_positions(width, height, step):
        cx, cy = m["px"], m["py"]
        img.fill_rect(cx - CLEAR_HALF, cy - CLEAR_HALF, cx + CLEAR_HALF + 1, cy + CLEAR_HALF + 1, CLEAR)
        color = CORNER_COLORS.get(m["corner"], WHITE)
        img.fill_rect(cx - MARKER_HALF, cy - MARKER_HALF, cx + MARKER_HALF + 1, cy + MARKER_HALF + 1, color)
    return img
