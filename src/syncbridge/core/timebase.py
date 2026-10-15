"""Frame rates and frame <-> seconds conversion.

Frame rates are held as exact rationals (fractions.Fraction) so that NTSC
rates such as 24000/1001 do not drift. Internally all curve math is done in
seconds (float); frame numbers only appear at the application boundary.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Sequence, Union

# Rates that float frame rates (e.g. AE's comp.frameRate = 23.976023976...)
# are snapped to when they are close enough.
KNOWN_RATES = (
    Fraction(24000, 1001), Fraction(30000, 1001), Fraction(48000, 1001),
    Fraction(60000, 1001), Fraction(120000, 1001),
    Fraction(8), Fraction(10), Fraction(12), Fraction(12.5), Fraction(15), Fraction(16),
    Fraction(20), Fraction(24), Fraction(25), Fraction(30), Fraction(48), Fraction(50),
    Fraction(60), Fraction(72), Fraction(75), Fraction(80), Fraction(90), Fraction(100),
    Fraction(120), Fraction(240),
)

# Maya `currentUnit -q -time` names. Source: Maya currentUnit command docs.
# The "Nfps" form (e.g. "23.976fps", "12fps") is parsed generically.
MAYA_TIME_UNITS = {
    "game": Fraction(15),
    "film": Fraction(24),
    "pal": Fraction(25),
    "ntsc": Fraction(30),
    "show": Fraction(48),
    "palf": Fraction(50),
    "ntscf": Fraction(60),
    "29.97df": Fraction(30000, 1001),
}

_SNAP_TOLERANCE = 1e-4

FpsLike = Union["FrameRate", Fraction, int, float, str, Sequence[int]]


class FrameRate:
    """An exact frame rate (frames per second)."""

    __slots__ = ("_rate",)

    def __init__(self, rate: FpsLike):
        self._rate = _to_fraction(rate)
        if self._rate <= 0:
            raise ValueError("frame rate must be positive: %r" % (rate,))

    @property
    def fraction(self) -> Fraction:
        return self._rate

    @property
    def fps(self) -> float:
        return float(self._rate)

    @property
    def frame_duration(self) -> float:
        """Seconds per frame."""
        return float(1 / self._rate)

    def frames_to_seconds(self, frames: float) -> float:
        return frames / float(self._rate)

    def seconds_to_frames(self, seconds: float) -> float:
        return seconds * float(self._rate)

    def to_json(self) -> list:
        return [self._rate.numerator, self._rate.denominator]

    @classmethod
    def from_json(cls, data) -> "FrameRate":
        return cls(data)

    @classmethod
    def from_ae(cls, frame_rate: float, frame_duration: float = None) -> "FrameRate":
        """Frame rate of an AE comp / footage.

        AE probe (AE 26.5, 2026-10-16): a "29.97" comp reported
        frameDuration = 1/29.97 and a duration of exactly 330 frames at
        1/29.97, i.e. AE's 29.97 is 2997/100, not 30000/1001 (H-AE-9). So the
        float is read as a decimal rate and, when frameDuration is given, the
        candidate that best matches it is used.
        """
        decimal = Fraction(frame_rate).limit_denominator(1000)
        candidates = [decimal, snap_rate(frame_rate)]
        if frame_duration:
            best = min(candidates, key=lambda c: abs(float(1 / c) - frame_duration))
        else:
            best = decimal
        return cls(best)

    @classmethod
    def from_maya_unit(cls, unit: str) -> "FrameRate":
        """Parse a Maya time unit name ("film", "ntsc", "23.976fps", ...)."""
        if unit in MAYA_TIME_UNITS:
            return cls(MAYA_TIME_UNITS[unit])
        if unit.endswith("fps"):
            return cls(snap_rate(float(unit[:-3])))
        raise ValueError("unsupported Maya time unit: %r" % unit)

    def __eq__(self, other) -> bool:
        if isinstance(other, FrameRate):
            return self._rate == other._rate
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._rate)

    def __repr__(self) -> str:
        r = self._rate
        if r.denominator == 1:
            return "FrameRate(%d)" % r.numerator
        return "FrameRate(%d/%d)" % (r.numerator, r.denominator)


def snap_rate(value: float) -> Fraction:
    """Snap a float frame rate to a known exact rate when within tolerance."""
    for known in KNOWN_RATES:
        if abs(float(known) - value) < _SNAP_TOLERANCE:
            return known
    return Fraction(value).limit_denominator(1001)


def _to_fraction(rate: FpsLike) -> Fraction:
    if isinstance(rate, FrameRate):
        return rate.fraction
    if isinstance(rate, Fraction):
        return rate
    if isinstance(rate, int):
        return Fraction(rate)
    if isinstance(rate, float):
        return snap_rate(rate)
    if isinstance(rate, str):
        if "/" in rate:
            num, den = rate.split("/")
            return Fraction(int(num), int(den))
        return snap_rate(float(rate))
    if isinstance(rate, (list, tuple)) and len(rate) == 2:
        return Fraction(int(rate[0]), int(rate[1]))
    raise TypeError("cannot interpret frame rate: %r" % (rate,))
