"""Read / write an animCurveTT in SyncBridge's Maya-native key format.

Must be called from Maya's main thread.

Verification status (docs/PHASE0_RESEARCH.md):
  * maya.cmds flags used here are documented in the Maya 2023 command
    reference, but this module has NOT yet been run on Maya.
  * H-MY-3: keyframe -valueChange / -eval on a TT curve return values in the
    current time unit (frames).
  * H-MY-4: for a TT curve tan(tangent angle) is the dimensionless slope
    d(out)/d(in).
  * H-MY-5: weighted handle extent along time = weight * cos(angle) * scale.
    The scale is unknown; read_curve() calibrates it against Maya's own
    evaluation, and probe.py reports which scale matches.
  * H-MY-6: setKeyframe accepts an animCurve node name directly.
"""
from __future__ import annotations

import math

from maya import cmds

from syncbridge.core import maya_codec
from syncbridge.core.timebase import FrameRate
from syncbridge.core.validation import compare_samples

# Candidate multipliers for H-MY-5 (handle_x_frames = weight * cos(angle) * c).
# Expressed as functions of fps because the weight unit may be seconds-based.
WEIGHT_SCALE_CANDIDATES = {
    "w/3 (frames)": lambda fps: 1.0 / 3.0,
    "w (frames)": lambda fps: 1.0,
    "w/3 (seconds)": lambda fps: fps / 3.0,
    "w (seconds)": lambda fps: fps,
}
# Used for writing until the probe confirms the real one (H-MY-5).
DEFAULT_WEIGHT_SCALE = "w/3 (frames)"


def scene_fps() -> FrameRate:
    return FrameRate.from_maya_unit(cmds.currentUnit(q=True, time=True))


def read_raw(curve: str) -> dict:
    """Query the curve's keys and tangents as Maya reports them (no conversion)."""
    q = dict(q=True)
    n = cmds.keyframe(curve, keyframeCount=True, **q) or 0
    if n == 0:
        return {"keys": []}
    return {
        "times": cmds.keyframe(curve, timeChange=True, **q),
        "values": cmds.keyframe(curve, valueChange=True, **q),
        "inTangentType": cmds.keyTangent(curve, inTangentType=True, **q),
        "outTangentType": cmds.keyTangent(curve, outTangentType=True, **q),
        "inAngle": cmds.keyTangent(curve, inAngle=True, **q),
        "outAngle": cmds.keyTangent(curve, outAngle=True, **q),
        "inWeight": cmds.keyTangent(curve, inWeight=True, **q),
        "outWeight": cmds.keyTangent(curve, outWeight=True, **q),
        "weighted": bool((cmds.keyTangent(curve, weightedTangents=True, **q) or [False])[0]),
        "preInfinity": cmds.setInfinity(curve, preInfinite=True, **q)[0],
        "postInfinity": cmds.setInfinity(curve, postInfinite=True, **q)[0],
    }


def raw_to_native(raw: dict, fps: FrameRate, weight_scale: str = DEFAULT_WEIGHT_SCALE) -> dict:
    """Convert read_raw() output to the Maya-native dict of syncbridge.core.maya_codec."""
    scale = WEIGHT_SCALE_CANDIDATES[weight_scale](fps.fps)
    keys = []
    for i, t in enumerate(raw.get("times", [])):
        ia, oa = math.radians(raw["inAngle"][i]), math.radians(raw["outAngle"][i])
        k = {
            "time": t, "value": raw["values"][i],
            "inTangentType": raw["inTangentType"][i], "outTangentType": raw["outTangentType"][i],
            "inSlope": math.tan(ia), "outSlope": math.tan(oa),
        }
        if raw.get("weighted"):
            k["inHandleX"] = raw["inWeight"][i] * math.cos(ia) * scale
            k["outHandleX"] = raw["outWeight"][i] * math.cos(oa) * scale
        keys.append(k)
    warnings = []
    for side in ("preInfinity", "postInfinity"):
        if raw.get(side) not in (None, "constant", "linear"):
            warnings.append("%s %r is not supported; treated as constant" % (side, raw.get(side)))
    return {
        "fps": fps.to_json(),
        "weighted": bool(raw.get("weighted")),
        "preInfinity": _infinity(raw.get("preInfinity")),
        "postInfinity": _infinity(raw.get("postInfinity")),
        "keys": keys,
        "warnings": warnings,
    }


def sample(curve: str, frames) -> list:
    """Evaluate the curve at (sub-)frame times with Maya itself (ground truth)."""
    return [cmds.keyframe(curve, q=True, eval=True, time=(f, f))[0] for f in frames]


def sample_frames(raw: dict, oversample: int = 4, frame_range=None) -> list:
    if frame_range is None:
        frame_range = (min(raw["times"]), max(raw["times"]))
    lo, hi = frame_range
    n = int(round((hi - lo) * oversample))
    frames = [lo + i / float(oversample) for i in range(n + 1)]
    frames.extend(t for t in raw["times"] if lo <= t <= hi)
    return sorted(set(frames))


def read_curve(curve: str, oversample: int = 4, frame_range=None):
    """Read curve -> (native dict, samples dict, calibration info).

    For weighted curves every H-MY-5 candidate is tried and the one whose
    decoded curve best matches Maya's own evaluation is used.
    """
    fps = scene_fps()
    raw = read_raw(curve)
    if not raw.get("times"):
        raise RuntimeError("%s has no keys" % curve)
    frames = sample_frames(raw, oversample, frame_range)
    values = sample(curve, frames)
    samples = {"times": frames, "values": values}
    candidates = list(WEIGHT_SCALE_CANDIDATES) if raw["weighted"] else [DEFAULT_WEIGHT_SCALE]
    best = None
    for name in candidates:
        native = raw_to_native(raw, fps, name)
        curve_s = maya_codec.decode(native)
        spf = fps.frame_duration
        report = compare_samples([f * spf for f in frames], [v * spf for v in values],
                                 curve_s.evaluate, fps.to_json())
        if best is None or report.max_error_frames < best[2].max_error_frames:
            best = (name, native, report)
    calibration = {"weight_scale": best[0], "decode_vs_maya": best[2].to_json()}
    return best[1], samples, calibration


def write_curve(curve: str, native: dict, weight_scale: str = DEFAULT_WEIGHT_SCALE) -> None:
    """Replace the keys of an existing animCurveTT with `native` (frames of the scene fps).

    New keys are set first and stale keys removed afterwards so the curve
    node never becomes empty (an empty curve might be deleted by Maya).
    Call inside an undo chunk; back up first (see exchange.apply_timewarp).
    """
    fps = scene_fps()
    if FrameRate(native["fps"]) != fps:
        raise ValueError("native fps %s != scene fps %s" % (native["fps"], fps.to_json()))
    keys = native["keys"]
    new_times = [k["time"] for k in keys]
    old_times = cmds.keyframe(curve, q=True, timeChange=True) or []

    for k in keys:
        cmds.setKeyframe(curve, time=k["time"], value=k["value"])  # H-MY-6
    for t in old_times:
        if all(abs(t - nt) > 1e-6 for nt in new_times):
            cmds.cutKey(curve, time=(t, t), clear=True)

    weighted = bool(native.get("weighted"))
    cmds.keyTangent(curve, edit=True, weightedTangents=weighted)
    scale = WEIGHT_SCALE_CANDIDATES[weight_scale](fps.fps)
    for i, k in enumerate(keys):
        idx = (i, i)
        cmds.keyTangent(curve, edit=True, index=idx, lock=False)
        if weighted:
            cmds.keyTangent(curve, edit=True, index=idx, weightLock=False)
        in_type = k.get("inTangentType", "fixed")
        out_type = k.get("outTangentType", "fixed")
        args = {}
        if in_type == "fixed":
            args["inAngle"] = math.degrees(math.atan(k["inSlope"]))
            if weighted and k.get("inHandleX"):
                args["inWeight"] = k["inHandleX"] / (math.cos(math.radians(args["inAngle"])) * scale)
        if out_type == "fixed":
            args["outAngle"] = math.degrees(math.atan(k["outSlope"]))
            if weighted and k.get("outHandleX"):
                args["outWeight"] = k["outHandleX"] / (math.cos(math.radians(args["outAngle"])) * scale)
        cmds.keyTangent(curve, edit=True, index=idx, inTangentType=in_type, outTangentType=out_type)
        if args:
            cmds.keyTangent(curve, edit=True, index=idx, **args)

    cmds.setInfinity(curve, preInfinite=native.get("preInfinity", "constant"),
                     postInfinite=native.get("postInfinity", "constant"))


def _infinity(value) -> str:
    # setInfinity -q returns "constant", "linear", "cycle", ... ; only the first two are supported.
    return value if value in ("constant", "linear") else "constant"
