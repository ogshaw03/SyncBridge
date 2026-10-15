"""Reference time mapping curves used by unit tests and by the Maya/AE probes.

All curves are in seconds and cover typical time warp situations: normal
playback, slow motion, fast forward, freeze (hold), reverse playback,
non-monotonic eases and NTSC rates. Bezier handles are written explicitly so
the probes can check how each application interprets them.
"""
from __future__ import annotations

from typing import Callable, Dict

from .curve import Extrapolation, Interp, Key, TimeCurve

B, L, H = Interp.BEZIER, Interp.LINEAR, Interp.HOLD


def identity() -> TimeCurve:
    return TimeCurve([Key(0.0, 0.0), Key(4.0, 4.0)])


def slowmo_linear() -> TimeCurve:
    """Normal speed, then 50% slow motion, then normal again."""
    return TimeCurve([Key(0.0, 0.0), Key(1.0, 1.0), Key(3.0, 2.0), Key(4.0, 3.0)])


def speed_ramp_bezier() -> TimeCurve:
    """Smooth ramp from 1x to 3x and back (Hermite-like 1/3 handles)."""
    return TimeCurve([
        Key(0.0, 0.0, L, B, None, (0.5, 0.5)),
        Key(1.5, 3.0, B, B, (-0.5, -1.5), (0.5, 1.5)),
        Key(3.0, 6.0, B, L, (-0.5, -0.5), None),
    ])


def asymmetric_ease() -> TimeCurve:
    """Handles that are NOT 1/3 of the segment (weighted / AE influence != 33%)."""
    return TimeCurve([
        Key(0.0, 0.0, L, B, None, (1.6, 0.0)),        # influence 80%, ease-in from stop
        Key(2.0, 2.0, B, B, (-0.2, -0.3), (0.3, 0.45)),
        Key(3.0, 4.0, B, L, (-0.9, -0.2), None),
    ])


def freeze_hold() -> TimeCurve:
    """Play, freeze for 1s, then continue."""
    return TimeCurve([
        Key(0.0, 0.0), Key(1.0, 1.0, L, H), Key(2.0, 1.0), Key(3.0, 2.0),
    ])


def jump_hold() -> TimeCurve:
    """Hold followed by a discontinuous jump (cut inside the remap)."""
    return TimeCurve([
        Key(0.0, 0.0), Key(1.0, 1.0, L, H), Key(2.0, 3.0), Key(3.0, 4.0),
    ])


def reverse() -> TimeCurve:
    """Forward, then reverse playback, then forward."""
    return TimeCurve([Key(0.0, 0.0), Key(1.0, 1.0), Key(2.0, 0.5), Key(3.0, 1.5)])


def nonmonotonic_bezier() -> TimeCurve:
    """Bezier overshoot: output goes forward, back, forward."""
    return TimeCurve([
        Key(0.0, 0.0, L, B, None, (0.6, 2.0)),
        Key(2.0, 1.0, B, L, (-0.6, 1.0), None),
    ])


def linear_then_ease() -> TimeCurve:
    """Interior keys with a LINEAR side and a BEZIER side (linear -> eased -> linear)."""
    return TimeCurve([
        Key(0.0, 0.0),
        Key(1.0, 1.0, L, B, None, (0.4, 0.8)),
        Key(2.0, 1.5, B, L, (-0.3, -0.1), None),
        Key(3.0, 2.5),
    ])


def subframe_keys() -> TimeCurve:
    """Keys between frames at 24 fps (frame 24.5 and 48.25), for H-AE-5."""
    return TimeCurve([Key(0.0, 0.0), Key(24.5 / 24.0, 1.5), Key(48.25 / 24.0, 2.0), Key(3.0, 3.0)])


def linear_infinity() -> TimeCurve:
    """Maya-style linear pre/post infinity (not representable in AE)."""
    return TimeCurve([Key(1.0, 1.0), Key(2.0, 1.5)],
                     Extrapolation.LINEAR, Extrapolation.LINEAR)


CURVES: Dict[str, Callable[[], TimeCurve]] = {
    "identity": identity,
    "slowmo_linear": slowmo_linear,
    "speed_ramp_bezier": speed_ramp_bezier,
    "asymmetric_ease": asymmetric_ease,
    "freeze_hold": freeze_hold,
    "jump_hold": jump_hold,
    "reverse": reverse,
    "nonmonotonic_bezier": nonmonotonic_bezier,
    "linear_then_ease": linear_then_ease,
    "subframe_keys": subframe_keys,
}
# Curves the probes push into the apps (linear_infinity is Maya-only).
PROBE_CURVES = dict(CURVES)


# AE-native key lists sent to AE as-is (not produced by ae_codec.encode).
# ae_mixed_linear_bezier: segments with a LINEAR side and a BEZIER side, whose
# LINEAR side carries a non-trivial ease. Tests how AE evaluates it (H-AE-6);
# the codec assumes the LINEAR side behaves like a handle at 1/3 of the chord.
AE_RAW_PROBE_VECTORS = {
    "ae_mixed_linear_bezier": [
        {"time": 0.0, "value": 0.0, "inInterp": "LINEAR", "outInterp": "LINEAR",
         "inEase": {"speed": 0.0, "influence": 33.333333}, "outEase": {"speed": 0.2, "influence": 50.0}},
        {"time": 2.0, "value": 2.0, "inInterp": "BEZIER", "outInterp": "BEZIER",
         "inEase": {"speed": 0.0, "influence": 60.0}, "outEase": {"speed": 0.0, "influence": 33.333333}},
        {"time": 3.0, "value": 3.0, "inInterp": "LINEAR", "outInterp": "LINEAR",
         "inEase": {"speed": 3.0, "influence": 50.0}, "outEase": {"speed": 0.0, "influence": 33.333333}},
    ],
}
