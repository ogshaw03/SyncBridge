"""Maya animCurveTT (Scene Time Warp curve) keys <-> neutral TimeCurve.

Maya-native key format (what maya_plugin exports / applies). It is unit
explicit: times and values are in *frames* of `fps`, slopes are
d(value frames)/d(time frames) (dimensionless for a time->time curve), and
handle extents are in frames along the time axis.

    {"time": frame, "value": frame,
     "inTangentType": "spline"|"linear"|"step"|"fixed"|...,
     "outTangentType": ...,
     "inSlope": float, "outSlope": float,
     "inHandleX": frames (>0, weighted curves only), "outHandleX": frames}

    curve-level: {"fps": [num, den], "weighted": bool,
                  "preInfinity": "constant"|"linear", "postInfinity": ...}

Mapping Maya tangent angle/weight to slope/handle extent is done in the Maya
adapter, and is verified on the real application by the Maya probe
(hypotheses H-MY-4/5 in docs/PHASE0_RESEARCH.md).

Segment model (Maya devkit animEngine): a non-weighted segment is a Hermite
cubic, which equals a Bezier with handles at 1/3 of the segment length;
a weighted segment is a Bezier with explicit handle extents.
"""
from __future__ import annotations

from typing import List

from .ae_codec import EncodeReport
from .curve import Extrapolation, Interp, Key, TimeCurve
from .timebase import FrameRate

STEP_TYPES = ("step",)
UNSUPPORTED_TYPES = ("stepnext",)
_EPS = 1e-9


def decode(native: dict, report: EncodeReport = None) -> TimeCurve:
    """Maya-native curve dict -> TimeCurve in seconds."""
    report = report if report is not None else EncodeReport()
    rate = FrameRate(native["fps"])
    weighted = bool(native.get("weighted", False))
    mkeys = sorted(native["keys"], key=lambda k: k["time"])
    keys: List[Key] = []
    for i, mk in enumerate(mkeys):
        for side in ("inTangentType", "outTangentType"):
            if mk.get(side) in UNSUPPORTED_TYPES:
                report.warnings.append("key %d: tangent type %r not supported in Editable "
                                       "mode; use Precision mode" % (i, mk.get(side)))
        out_type = mk.get("outTangentType", "spline")
        in_type = mk.get("inTangentType", "spline")
        out_interp = Interp.HOLD if out_type in STEP_TYPES else Interp.BEZIER
        in_interp = Interp.BEZIER
        if in_type == "linear" and i > 0 and mkeys[i - 1].get("outTangentType") == "linear":
            in_interp = Interp.LINEAR
        if out_type == "linear" and i < len(mkeys) - 1 and mkeys[i + 1].get("inTangentType") == "linear":
            out_interp = Interp.LINEAR
        in_handle = out_handle = None
        if i > 0:
            dt = mk["time"] - mkeys[i - 1]["time"]
            hx = float(mk["inHandleX"]) if weighted and mk.get("inHandleX") else dt / 3.0
            in_handle = (-hx, -float(mk.get("inSlope", 0.0)) * hx)
        if i < len(mkeys) - 1:
            dt = mkeys[i + 1]["time"] - mk["time"]
            hx = float(mk["outHandleX"]) if weighted and mk.get("outHandleX") else dt / 3.0
            out_handle = (hx, float(mk.get("outSlope", 0.0)) * hx)
        keys.append(Key(mk["time"], mk["value"], in_interp, out_interp, in_handle, out_handle))
    curve = TimeCurve(
        keys,
        Extrapolation(native.get("preInfinity", "constant")),
        Extrapolation(native.get("postInfinity", "constant")),
    )
    # Frames -> seconds. Slopes are invariant because both axes scale equally.
    spf = rate.frame_duration
    return curve.affine(in_scale=spf, out_scale=spf)


def encode(curve: TimeCurve, fps, report: EncodeReport = None) -> dict:
    """TimeCurve (seconds) -> Maya-native dict in frames of `fps`.

    Every non-hold key side gets tangent type "fixed" so Maya does not
    recompute it. A weighted curve is emitted only if some handle extent is
    not 1/3 of its segment (Maya non-weighted tangents cannot express it).
    """
    report = report if report is not None else EncodeReport()
    rate = FrameRate(fps)
    if curve.pre_infinity.value not in ("constant", "linear"):
        report.warnings.append("unsupported pre infinity")
    fr = curve.affine(in_scale=rate.fps, out_scale=rate.fps)
    keys = fr.keys
    n = len(keys)
    mkeys = []
    weighted = False
    for i, k in enumerate(keys):
        mk = {"time": k.t, "value": k.v,
              "inTangentType": "fixed", "outTangentType": "fixed",
              "inSlope": 0.0, "outSlope": 0.0}
        if i > 0:
            if fr.segment_is_hold(i - 1):
                # In-tangent of a key after a held segment has no effect; "step"
                # is only documented as an out-tangent type, so use linear.
                mk["inTangentType"] = "linear"
            elif fr.segment_is_linear(i - 1):
                mk["inTangentType"] = "linear"
                mk["inSlope"] = (k.v - keys[i - 1].v) / (k.t - keys[i - 1].t)
            else:
                _, _, p2, p3 = fr.segment_bezier(i - 1)
                hx, slope = _handle(p3[0] - p2[0], p3[1] - p2[1], i, report)
                mk["inSlope"], mk["inHandleX"] = slope, hx
                weighted |= abs(hx - (k.t - keys[i - 1].t) / 3.0) > 1e-6
        if i < n - 1:
            if fr.segment_is_hold(i):
                mk["outTangentType"] = "step"
            elif fr.segment_is_linear(i):
                mk["outTangentType"] = "linear"
                mk["outSlope"] = (keys[i + 1].v - k.v) / (keys[i + 1].t - k.t)
            else:
                p0, p1, _, _ = fr.segment_bezier(i)
                hx, slope = _handle(p1[0] - p0[0], p1[1] - p0[1], i, report)
                mk["outSlope"], mk["outHandleX"] = slope, hx
                weighted |= abs(hx - (keys[i + 1].t - k.t) / 3.0) > 1e-6
        mkeys.append(mk)
    if not weighted:
        for mk in mkeys:
            mk.pop("inHandleX", None)
            mk.pop("outHandleX", None)
    return {
        "fps": rate.to_json(),
        "weighted": weighted,
        "preInfinity": curve.pre_infinity.value,
        "postInfinity": curve.post_infinity.value,
        "keys": mkeys,
    }


def _handle(dx: float, dy: float, index: int, report: EncodeReport):
    if dx <= _EPS:
        report.warnings.append("key %d: vertical tangent cannot be represented exactly" % index)
        report.clamped_keys.append(index)
        dx = 1e-4
    return dx, dy / dx
