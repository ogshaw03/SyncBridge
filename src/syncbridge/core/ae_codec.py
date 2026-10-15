"""After Effects Time Remap keyframes <-> neutral TimeCurve.

AE-native key format (what after_effects/jsx exports / applies), times and
values in seconds:

    {"time": comp_seconds, "value": source_seconds,
     "inInterp": "LINEAR"|"BEZIER"|"HOLD", "outInterp": ...,
     "inEase": {"speed": float, "influence": percent},
     "outEase": {"speed": float, "influence": percent}}

Temporal ease -> Bezier handle (hypothesis H-AE-3, docs/PHASE0_RESEARCH.md):
    out handle of key i : dx = influence/100 * (t_{i+1} - t_i), dy = speed * dx
    in  handle of key i : dx = -influence/100 * (t_i - t_{i-1}), dy = speed * dx
For Time Remap, speed is (source seconds) / (comp second), i.e. dimensionless.
Influence is limited to [0.1, 100] percent in AE.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .curve import Interp, Key, TimeCurve

AE_MIN_INFLUENCE = 0.1
AE_MAX_INFLUENCE = 100.0
DEFAULT_INFLUENCE = 100.0 / 3.0

_AE_INTERP = {"LINEAR": Interp.LINEAR, "BEZIER": Interp.BEZIER, "HOLD": Interp.HOLD}
_INTERP_AE = {v: k for k, v in _AE_INTERP.items()}


@dataclass
class EncodeReport:
    """Notes about lossy steps taken while encoding to an app format."""
    warnings: List[str] = field(default_factory=list)
    clamped_keys: List[int] = field(default_factory=list)

    @property
    def lossless(self) -> bool:
        return not self.warnings


def decode(ae_keys: List[dict]) -> TimeCurve:
    """AE-native keys -> TimeCurve (AE time remap has constant extrapolation)."""
    ae_keys = sorted(ae_keys, key=lambda k: k["time"])
    keys: List[Key] = []
    n = len(ae_keys)
    for i, k in enumerate(ae_keys):
        in_interp = _AE_INTERP[k.get("inInterp", "LINEAR")]
        out_interp = _AE_INTERP[k.get("outInterp", "LINEAR")]
        in_handle = out_handle = None
        if in_interp == Interp.BEZIER and i > 0:
            dt = k["time"] - ae_keys[i - 1]["time"]
            ease = k.get("inEase") or {}
            dx = -float(ease.get("influence", DEFAULT_INFLUENCE)) / 100.0 * dt
            in_handle = (dx, float(ease.get("speed", 0.0)) * dx)
        if out_interp == Interp.BEZIER and i < n - 1:
            dt = ae_keys[i + 1]["time"] - k["time"]
            ease = k.get("outEase") or {}
            dx = float(ease.get("influence", DEFAULT_INFLUENCE)) / 100.0 * dt
            out_handle = (dx, float(ease.get("speed", 0.0)) * dx)
        keys.append(Key(float(k["time"]), float(k["value"]), in_interp, out_interp,
                        in_handle, out_handle))
    return TimeCurve(keys)


def encode(curve: TimeCurve, report: EncodeReport = None) -> List[dict]:
    """TimeCurve -> AE-native keys. Lossy steps are recorded in `report`."""
    report = report if report is not None else EncodeReport()
    if curve.pre_infinity.value != "constant" or curve.post_infinity.value != "constant":
        report.warnings.append("AE Time Remap holds values outside the key range; "
                               "linear pre/post infinity is not representable")
    keys = curve.keys
    out: List[dict] = []
    for i, k in enumerate(keys):
        in_interp, out_interp = k.in_interp, k.out_interp
        in_ease = {"speed": 0.0, "influence": DEFAULT_INFLUENCE}
        out_ease = {"speed": 0.0, "influence": DEFAULT_INFLUENCE}
        if i > 0 and not curve.segment_is_hold(i - 1) and not curve.segment_is_linear(i - 1):
            # Incoming Bezier side: express P2 - P3 as ease.
            _, _, p2, p3 = curve.segment_bezier(i - 1)
            in_ease = _ease(p3[0] - p2[0], p3[1] - p2[1], k.t - keys[i - 1].t, i, report)
            in_interp = Interp.BEZIER
        if i < len(keys) - 1 and not curve.segment_is_hold(i) and not curve.segment_is_linear(i):
            p0, p1, _, _ = curve.segment_bezier(i)
            out_ease = _ease(p1[0] - p0[0], p1[1] - p0[1], keys[i + 1].t - k.t, i, report)
            out_interp = Interp.BEZIER
        if i < len(keys) - 1 and curve.segment_is_hold(i):
            out_interp = Interp.HOLD
        if in_interp == Interp.HOLD:
            # Neutral "in HOLD" is folded into the previous key's out HOLD above.
            in_interp = Interp.LINEAR
        out.append({
            "time": k.t, "value": k.v,
            "inInterp": _INTERP_AE[in_interp], "outInterp": _INTERP_AE[out_interp],
            "inEase": in_ease, "outEase": out_ease,
        })
    return out


def _ease(dx: float, dy: float, seg_dt: float, index: int, report: EncodeReport) -> dict:
    """Handle extent (dx >= 0 along time, dy) -> AE KeyframeEase values."""
    influence = dx / seg_dt * 100.0
    if influence < AE_MIN_INFLUENCE:
        # Keep the handle direction as well as possible with the minimum length.
        speed = dy / (AE_MIN_INFLUENCE / 100.0 * seg_dt) if dx <= 0 else dy / dx
        report.warnings.append("key %d: influence %.4f%% raised to AE minimum %.1f%%"
                               % (index, influence, AE_MIN_INFLUENCE))
        report.clamped_keys.append(index)
        return {"speed": speed, "influence": AE_MIN_INFLUENCE}
    influence = min(influence, AE_MAX_INFLUENCE)
    return {"speed": dy / dx, "influence": influence}
