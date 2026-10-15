"""Error measurement between time mapping curves.

Errors are reported in *output frames* at a given frame rate, because the
acceptance criterion is "warped time differs by <= 0.1 frame".
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

from .timebase import FrameRate

Evaluator = Callable[[float], float]
DEFAULT_TOLERANCE_FRAMES = 0.1
_MAX_REPORTED_EXCEEDANCES = 50


@dataclass
class ErrorReport:
    tolerance_frames: float
    max_error_frames: float = 0.0
    mean_error_frames: float = 0.0
    rms_error_frames: float = 0.0
    worst_time: Optional[float] = None
    sample_count: int = 0
    exceed_count: int = 0
    exceedances: List[Tuple[float, float]] = field(default_factory=list)  # (time s, error frames)

    @property
    def passed(self) -> bool:
        return self.max_error_frames <= self.tolerance_frames + 1e-9

    def to_json(self) -> dict:
        d = asdict(self)
        d["passed"] = self.passed
        return d

    def summary(self) -> str:
        return ("%s max=%.5f f mean=%.5f f rms=%.5f f worst@%s s samples=%d tol=%.3f f"
                % ("PASS" if self.passed else "FAIL", self.max_error_frames,
                   self.mean_error_frames, self.rms_error_frames,
                   "-" if self.worst_time is None else "%.5f" % self.worst_time,
                   self.sample_count, self.tolerance_frames))


def sample_times(t0: float, t1: float, fps, oversample: int = 8,
                 extra: Iterable[float] = ()) -> List[float]:
    """Uniform times from t0 to t1 inclusive at fps*oversample, plus `extra` points."""
    if t1 < t0:
        raise ValueError("t1 < t0")
    step = FrameRate(fps).frame_duration / oversample
    n = int(math.floor((t1 - t0) / step + 1e-9))
    times = {t0 + i * step for i in range(n + 1)}
    times.add(t1)
    times.update(t for t in extra if t0 <= t <= t1)
    return sorted(times)


def compare_at(times: Sequence[float], a: Evaluator, b: Evaluator, fps,
               tolerance_frames: float = DEFAULT_TOLERANCE_FRAMES) -> ErrorReport:
    """Compare two evaluators at the given times."""
    values_a = [a(t) for t in times]
    return compare_samples(times, values_a, b, fps, tolerance_frames)


def compare_samples(times: Sequence[float], values: Sequence[float], b: Evaluator, fps,
                    tolerance_frames: float = DEFAULT_TOLERANCE_FRAMES) -> ErrorReport:
    """Compare reference samples (e.g. read back from Maya/AE) to an evaluator."""
    rate = FrameRate(fps).fps
    report = ErrorReport(tolerance_frames=tolerance_frames)
    total = total_sq = 0.0
    for t, v in zip(times, values):
        err = abs(v - b(t)) * rate
        total += err
        total_sq += err * err
        if report.worst_time is None or err > report.max_error_frames:
            report.max_error_frames = err
            report.worst_time = t
        if err > tolerance_frames + 1e-9:
            report.exceed_count += 1
            if len(report.exceedances) < _MAX_REPORTED_EXCEEDANCES:
                report.exceedances.append((t, err))
    n = len(times)
    report.sample_count = n
    if n:
        report.mean_error_frames = total / n
        report.rms_error_frames = math.sqrt(total_sq / n)
    return report


def compare_curves(a, b, fps, tolerance_frames: float = DEFAULT_TOLERANCE_FRAMES,
                   oversample: int = 8, t_range: Optional[Tuple[float, float]] = None) -> ErrorReport:
    """Compare two curve-like objects (with .evaluate/.domain) over a range.

    Breakpoints (key times) of both curves are included so hold jumps and
    corners are always checked.
    """
    if t_range is None:
        da, db = a.domain, b.domain
        t_range = (min(da[0], db[0]), max(da[1], db[1]))
    extra = []
    for c in (a, b):
        if hasattr(c, "breakpoints"):
            extra.extend(c.breakpoints())
    times = sample_times(t_range[0], t_range[1], fps, oversample, extra)
    return compare_at(times, a.evaluate, b.evaluate, fps, tolerance_frames)
