"""Edits of a Maya Scene Time Warp curve that keep its shape (pure, no Maya imports).

    retime(native, new_start, new_end)  stretch / move the curve along scene time
    to_scene_fps(native, fps)           re-express a curve saved at another frame rate

`native` is the Maya-native dict of maya_codec (frames of native["fps"]).
Retiming is an affine map of the input (scene) time only: the output values
(which frame of the animation is shown) are unchanged, handles scale with
the time axis, so the curve keeps its shape (docs/SPEC.md 3.1, affine maps).
"""
from __future__ import annotations

from typing import Optional, Tuple

from . import maya_codec
from .timebase import FrameRate


def key_range(native: dict) -> Tuple[float, float]:
    """(first key time, last key time) in frames."""
    times = [k["time"] for k in native["keys"]]
    if not times:
        raise ValueError("the curve has no keys")
    return min(times), max(times)


def value_range(native: dict) -> Tuple[float, float]:
    values = [k["value"] for k in native["keys"]]
    return min(values), max(values)


def retime(native: dict, new_start: float, new_end: float,
           old_start: Optional[float] = None, old_end: Optional[float] = None) -> dict:
    """Map scene frames old_start..old_end (default: first..last key) onto new_start..new_end.

    Values are kept. Raises ValueError for an empty or reversed range.
    """
    if old_start is None or old_end is None:
        k0, k1 = key_range(native)
        old_start = k0 if old_start is None else old_start
        old_end = k1 if old_end is None else old_end
    if old_end <= old_start:
        raise ValueError("the curve spans a single frame; give old_start / old_end")
    if new_end <= new_start:
        raise ValueError("the new range must end after it starts (%g..%g)" % (new_start, new_end))
    rate = FrameRate(native["fps"])
    spf = rate.frame_duration
    scale = (new_end - new_start) / (old_end - old_start)
    curve = maya_codec.decode(native)                     # seconds
    moved = curve.affine(in_scale=scale, in_offset=(new_start - old_start * scale) * spf)
    out = maya_codec.encode(moved, native["fps"])
    # Key times and values exactly, in frames (the seconds round trip adds ~1e-14 noise).
    for new_key, old_key in zip(out["keys"], sorted(native["keys"], key=lambda k: k["time"])):
        new_key["time"] = new_start + (old_key["time"] - old_start) * scale
        new_key["value"] = old_key["value"]
    return out


def to_scene_fps(native: dict, fps) -> dict:
    """The same curve in seconds, expressed in frames of `fps` (a snapshot from another fps scene)."""
    if FrameRate(native["fps"]) == FrameRate(fps):
        return native
    return maya_codec.encode(maya_codec.decode(native), fps)
