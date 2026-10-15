"""Precision Mode: adaptive piecewise-linear resampling of a time curve.

Strategy (docs/ARCHITECTURE.md, design decision D-4): the result uses only
LINEAR and HOLD keys. Linear interpolation is evaluated identically by Maya
and AE, so the precision of the result does not depend on the (not yet
verified) tangent/ease conversion formulas.

Algorithm per continuous (non-hold) run of the source curve:
  * key candidates G: run ends + times on the grid 1/(fps*key_subdivision)
  * verification grid F: each G interval subdivided `verify_subdivision` times
  * recursive split: a line between two chosen keys is accepted when the
    error at every F point in between is <= FIT_MARGIN * tolerance; otherwise
    split at the G candidate nearest the worst F point. Where no G candidate
    is left, a sub-frame F point is used (allow_subframe).
  * the result is re-validated against the source over the whole range.
Hold segments are copied as HOLD keys at their exact times.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .curve import Interp, Key, TimeCurve
from .timebase import FrameRate
from .validation import DEFAULT_TOLERANCE_FRAMES, ErrorReport, compare_curves

# Fit tighter than the tolerance: the error between verification points can
# be slightly larger than at the points themselves.
FIT_MARGIN = 0.5


@dataclass
class PrecisionResult:
    curve: TimeCurve
    report: ErrorReport
    unreachable: List[Tuple[float, float]] = field(default_factory=list)  # (t0, t1) intervals


def fit_precision(curve: TimeCurve, fps,
                  tolerance_frames: float = DEFAULT_TOLERANCE_FRAMES,
                  key_subdivision: int = 1,
                  verify_subdivision: int = 8,
                  t_range: Optional[Tuple[float, float]] = None,
                  allow_subframe: bool = True) -> PrecisionResult:
    """Resample `curve` into LINEAR/HOLD keys within `tolerance_frames` (output frames at fps).

    key_subdivision=1 places keys only on whole frames (plus source
    breakpoints at run ends); raise it to allow sub-frame keys everywhere.
    allow_subframe=True lets the fitter fall back to a sub-frame key (on the
    verification grid) only where no key-grid candidate meets the tolerance.
    """
    rate = FrameRate(fps)
    tol_s = FIT_MARGIN * tolerance_frames * rate.frame_duration
    d0, d1 = curve.domain
    lo, hi = (d0, d1) if t_range is None else (min(t_range[0], d0), max(t_range[1], d1))

    runs: List[Tuple[float, float]] = []
    holds: List[int] = []
    if lo < d0:
        runs.append((lo, d0))
    start = d0
    for i in range(len(curve.keys) - 1):
        if curve.segment_is_hold(i):
            if curve.keys[i].t > start:
                runs.append((start, curve.keys[i].t))
            holds.append(i)
            start = curve.keys[i + 1].t
    if d1 > start:
        runs.append((start, d1))
    if hi > d1:
        runs.append((d1, hi))

    points: Dict[float, Key] = {}
    unreachable: List[Tuple[float, float]] = []
    step = rate.frame_duration / key_subdivision
    for a, b in runs:
        for t, v in _fit_run(curve, a, b, step, verify_subdivision, tol_s, unreachable,
                             allow_subframe):
            points.setdefault(t, Key(t, v))
    for i in holds:
        k0, k1 = curve.keys[i], curve.keys[i + 1]
        key = points.setdefault(k0.t, Key(k0.t, k0.v))
        key.out_interp = Interp.HOLD
        points.setdefault(k1.t, Key(k1.t, k1.v))
    if len(curve.keys) == 1:
        points.setdefault(d0, Key(d0, curve.keys[0].v))

    result = TimeCurve([points[t] for t in sorted(points)])
    report = compare_curves(curve, result, fps, tolerance_frames,
                            oversample=key_subdivision * verify_subdivision, t_range=(lo, hi))
    return PrecisionResult(result, report, unreachable)


def _fit_run(curve: TimeCurve, a: float, b: float, step: float, verify_sub: int,
             tol_s: float, unreachable: list, allow_subframe: bool = True) -> List[Tuple[float, float]]:
    # Key candidates on the absolute grid, strictly inside (a, b), plus the ends.
    first = int(math.floor(a / step + 1e-9)) + 1
    last = int(math.ceil(b / step - 1e-9)) - 1
    cand = [a] + [k * step for k in range(first, last + 1)
                  if a + 1e-9 < k * step < b - 1e-9] + [b]
    # Verification grid: each candidate interval split into verify_sub parts.
    fine_t: List[float] = []
    for t0, t1 in zip(cand, cand[1:]):
        for j in range(verify_sub):
            fine_t.append(t0 + (t1 - t0) * j / verify_sub)
    fine_t.append(b)
    # Runs contain no hold segments, so the curve is continuous on [a, b].
    fine_v = [curve.evaluate(t) for t in fine_t]
    # Work on fine-grid indices; indices that are multiples of verify_sub are
    # key-grid candidates and are preferred. A sub-frame (fine) index is used
    # only where no grid candidate can satisfy the tolerance.
    last_f = len(fine_t) - 1
    chosen = {0, last_f}
    stack = [(0, last_f)]
    while stack:
        fi, fj = stack.pop()
        ti, vi, tj, vj = fine_t[fi], fine_v[fi], fine_t[fj], fine_v[fj]
        slope = (vj - vi) / (tj - ti)
        worst_err, worst_f = 0.0, None
        for f in range(fi + 1, fj):
            err = abs(vi + slope * (fine_t[f] - ti) - fine_v[f])
            if err > worst_err:
                worst_err, worst_f = err, f
        if worst_err <= tol_s:
            continue
        k = _split_index(fi, fj, worst_f, verify_sub, allow_subframe)
        if k is None:
            unreachable.append((ti, tj))
            continue
        chosen.add(k)
        stack.append((fi, k))
        stack.append((k, fj))
    return [(fine_t[k], fine_v[k]) for k in sorted(chosen)]


def _split_index(fi: int, fj: int, worst_f: int, verify_sub: int, allow_subframe: bool):
    """Pick a split index strictly inside (fi, fj): nearest grid candidate, else worst_f."""
    k = int(round(worst_f / float(verify_sub))) * verify_sub
    if fi < k < fj:
        return k
    lo = (fi // verify_sub + 1) * verify_sub
    hi = ((fj - 1) // verify_sub) * verify_sub
    if lo <= hi:
        return min(max(k, lo), hi)
    if allow_subframe and fi < worst_f < fj:
        return worst_f
    return None
