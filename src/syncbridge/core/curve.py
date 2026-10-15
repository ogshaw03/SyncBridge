"""Application-neutral time mapping curve.

A TimeCurve maps *input time* (seconds) to *output time* (seconds):

    Maya Scene Time Warp : scene (unwarped) time  -> warped evaluation time
    AE Time Remap        : composition time       -> layer source time

Segment semantics (defined by SyncBridge, see docs/SPEC.md "Neutral curve"):

* Key i out == HOLD (or key i+1 in == HOLD): value stays v_i until t_{i+1}.
* Key i out == LINEAR and key i+1 in == LINEAR: straight line.
* Otherwise a 2D cubic Bezier
      P0 = (t_i, v_i)
      P1 = P0 + out_handle_i        (LINEAR side: P0 + chord / 3)
      P2 = P3 + in_handle_{i+1}     (LINEAR side: P3 - chord / 3)
      P3 = (t_{i+1}, v_{i+1})
  Handle x components are clamped into the segment so the curve stays a
  function of time.

Handles are explicit (dt, dv) offsets in seconds, which is the common
denominator of Maya tangents (slope + weight) and AE temporal ease
(speed + influence). Converting to/from those lives in codecs.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

Handle = Tuple[float, float]


class Interp(str, Enum):
    LINEAR = "linear"
    BEZIER = "bezier"
    HOLD = "hold"


class Extrapolation(str, Enum):
    CONSTANT = "constant"
    LINEAR = "linear"


@dataclass
class Key:
    t: float
    v: float
    in_interp: Interp = Interp.LINEAR
    out_interp: Interp = Interp.LINEAR
    in_handle: Optional[Handle] = None   # (dt <= 0, dv); None -> derived from chord
    out_handle: Optional[Handle] = None  # (dt >= 0, dv); None -> derived from chord

    def to_json(self) -> dict:
        d = {"t": self.t, "v": self.v, "in": self.in_interp.value, "out": self.out_interp.value}
        if self.in_handle is not None:
            d["ih"] = list(self.in_handle)
        if self.out_handle is not None:
            d["oh"] = list(self.out_handle)
        return d

    @classmethod
    def from_json(cls, d: dict) -> "Key":
        return cls(
            t=float(d["t"]),
            v=float(d["v"]),
            in_interp=Interp(d.get("in", "linear")),
            out_interp=Interp(d.get("out", "linear")),
            in_handle=tuple(d["ih"]) if d.get("ih") is not None else None,
            out_handle=tuple(d["oh"]) if d.get("oh") is not None else None,
        )


@dataclass
class TimeCurve:
    keys: List[Key] = field(default_factory=list)
    pre_infinity: Extrapolation = Extrapolation.CONSTANT
    post_infinity: Extrapolation = Extrapolation.CONSTANT

    def __post_init__(self):
        self.keys = sorted(self.keys, key=lambda k: k.t)
        for a, b in zip(self.keys, self.keys[1:]):
            if b.t - a.t <= 0:
                raise ValueError("duplicate key time: %r" % a.t)
        self._times = [k.t for k in self.keys]

    # -- queries ---------------------------------------------------------
    @property
    def domain(self) -> Tuple[float, float]:
        if not self.keys:
            raise ValueError("empty curve")
        return self.keys[0].t, self.keys[-1].t

    def breakpoints(self) -> List[float]:
        return list(self._times)

    def segment_is_hold(self, i: int) -> bool:
        return self.keys[i].out_interp == Interp.HOLD or self.keys[i + 1].in_interp == Interp.HOLD

    def segment_is_linear(self, i: int) -> bool:
        return (self.keys[i].out_interp == Interp.LINEAR
                and self.keys[i + 1].in_interp == Interp.LINEAR)

    def segment_bezier(self, i: int) -> Tuple[Handle, Handle, Handle, Handle]:
        """Return the 4 control points of segment i (clamped, chord-derived where needed)."""
        a, b = self.keys[i], self.keys[i + 1]
        dt, dv = b.t - a.t, b.v - a.v
        if a.out_interp == Interp.LINEAR or a.out_handle is None:
            oh = (dt / 3.0, dv / 3.0)
        else:
            oh = _clamp_handle(a.out_handle, dt)
        if b.in_interp == Interp.LINEAR or b.in_handle is None:
            ih = (-dt / 3.0, -dv / 3.0)
        else:
            ih = _clamp_handle((-b.in_handle[0], -b.in_handle[1]), dt)
            ih = (-ih[0], -ih[1])
        return (a.t, a.v), (a.t + oh[0], a.v + oh[1]), (b.t + ih[0], b.v + ih[1]), (b.t, b.v)

    # -- evaluation --------------------------------------------------------
    def evaluate(self, t: float) -> float:
        keys = self.keys
        if not keys:
            raise ValueError("empty curve")
        if len(keys) == 1:
            return keys[0].v
        if t <= keys[0].t:
            if self.pre_infinity == Extrapolation.LINEAR and t < keys[0].t:
                return keys[0].v + (t - keys[0].t) * self._edge_slope(0)
            return keys[0].v
        if t >= keys[-1].t:
            if self.post_infinity == Extrapolation.LINEAR and t > keys[-1].t:
                return keys[-1].v + (t - keys[-1].t) * self._edge_slope(len(keys) - 1)
            return keys[-1].v
        i = bisect.bisect_right(self._times, t) - 1
        return self._eval_segment(i, t)

    def evaluate_many(self, times: Iterable[float]) -> List[float]:
        return [self.evaluate(t) for t in times]

    def _eval_segment(self, i: int, t: float) -> float:
        a, b = self.keys[i], self.keys[i + 1]
        if self.segment_is_hold(i):
            return a.v
        if self.segment_is_linear(i):
            return a.v + (b.v - a.v) * (t - a.t) / (b.t - a.t)
        p0, p1, p2, p3 = self.segment_bezier(i)
        u = _solve_bezier_x(p0[0], p1[0], p2[0], p3[0], t)
        return _bezier(p0[1], p1[1], p2[1], p3[1], u)

    def _edge_slope(self, index: int) -> float:
        """Slope used for linear extrapolation at the first/last key."""
        if index == 0:
            if self.segment_is_hold(0):
                return 0.0
            p0, p1, _, p3 = self.segment_bezier(0)
            dx, dy = p1[0] - p0[0], p1[1] - p0[1]
            if abs(dx) < 1e-12:
                dx, dy = p3[0] - p0[0], p3[1] - p0[1]
            return dy / dx
        last = index - 1
        if self.segment_is_hold(last):
            return 0.0
        p0, _, p2, p3 = self.segment_bezier(last)
        dx, dy = p3[0] - p2[0], p3[1] - p2[1]
        if abs(dx) < 1e-12:
            dx, dy = p3[0] - p0[0], p3[1] - p0[1]
        return dy / dx

    # -- transforms ----------------------------------------------------------
    def affine(self, in_scale: float = 1.0, in_offset: float = 0.0,
               out_scale: float = 1.0, out_offset: float = 0.0) -> "TimeCurve":
        """Return a new curve with t' = t*in_scale + in_offset, v' = v*out_scale + out_offset.

        Cubic Bezier segments are closed under affine maps, so this is exact.
        in_scale must be positive (time direction is preserved).
        """
        if in_scale <= 0:
            raise ValueError("in_scale must be positive")

        def h(handle):
            if handle is None:
                return None
            return (handle[0] * in_scale, handle[1] * out_scale)

        keys = [replace(k, t=k.t * in_scale + in_offset, v=k.v * out_scale + out_offset,
                        in_handle=h(k.in_handle), out_handle=h(k.out_handle))
                for k in self.keys]
        return TimeCurve(keys, self.pre_infinity, self.post_infinity)

    # -- serialization ---------------------------------------------------------
    def to_json(self) -> dict:
        return {
            "pre_infinity": self.pre_infinity.value,
            "post_infinity": self.post_infinity.value,
            "keys": [k.to_json() for k in self.keys],
        }

    @classmethod
    def from_json(cls, d: dict) -> "TimeCurve":
        return cls(
            keys=[Key.from_json(k) for k in d["keys"]],
            pre_infinity=Extrapolation(d.get("pre_infinity", "constant")),
            post_infinity=Extrapolation(d.get("post_infinity", "constant")),
        )


class SampledCurve:
    """A curve known only by samples, evaluated with linear interpolation.

    Used for app read-back samples (Maya getAttr / AE valueAtTime) which are
    the ground truth of what each application actually evaluates.
    """

    def __init__(self, times: Sequence[float], values: Sequence[float]):
        if len(times) != len(values) or not times:
            raise ValueError("times/values must be non-empty and the same length")
        pairs = sorted(zip(times, values))
        self.times = [p[0] for p in pairs]
        self.values = [p[1] for p in pairs]

    @property
    def domain(self) -> Tuple[float, float]:
        return self.times[0], self.times[-1]

    def evaluate(self, t: float) -> float:
        ts = self.times
        if t <= ts[0]:
            return self.values[0]
        if t >= ts[-1]:
            return self.values[-1]
        i = bisect.bisect_right(ts, t) - 1
        t0, t1 = ts[i], ts[i + 1]
        v0, v1 = self.values[i], self.values[i + 1]
        return v0 + (v1 - v0) * (t - t0) / (t1 - t0)


Evaluator = Callable[[float], float]


# -- Bezier helpers ----------------------------------------------------------
def _clamp_handle(handle: Handle, dt: float) -> Handle:
    """Clamp an outgoing-style handle (dx >= 0) so 0 <= dx <= dt, keeping its slope."""
    dx, dy = handle
    if dx <= 0:
        # Vertical / backwards handle: keep direction of dy with a tiny dx.
        return (0.0, dy)
    if dx > dt:
        scale = dt / dx
        return (dt, dy * scale)
    return (dx, dy)


def _bezier(p0: float, p1: float, p2: float, p3: float, u: float) -> float:
    w = 1.0 - u
    return w * w * w * p0 + 3 * w * w * u * p1 + 3 * w * u * u * p2 + u * u * u * p3


def _solve_bezier_x(x0: float, x1: float, x2: float, x3: float, x: float) -> float:
    """Find u in [0, 1] with Bx(u) = x by bisection.

    With x0 <= x1, x2 <= x3 (guaranteed by handle clamping) a root exists by
    the intermediate value theorem; bisection is robust even if Bx is not
    strictly monotonic (overlapping handles).
    """
    lo, hi = 0.0, 1.0
    for _ in range(64):
        mid = 0.5 * (lo + hi)
        if _bezier(x0, x1, x2, x3, mid) < x:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
