"""High level Maya <-> AE time warp transfer (pure functions, no DCC imports).

Each transfer returns the target-native keys plus up to three error reports:

  source_fidelity : decoded source curve vs. samples the source app evaluated
                    (detects wrong assumptions about the source app's tangents)
  conversion      : target curve (re-decoded from the native keys we emit)
                    vs. the mapped source curve (detects codec / mode loss)
  readback        : filled in later by comparing samples the *target* app
                    evaluates after applying (see validate_readback)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from . import ae_codec, maya_codec
from .ae_codec import EncodeReport
from .curve import TimeCurve
from .mapping import MappingContext
from .sampler import fit_precision
from .timebase import FrameRate
from .validation import DEFAULT_TOLERANCE_FRAMES, ErrorReport, compare_curves, compare_samples

EDITABLE = "editable"
PRECISION = "precision"
MODES = (EDITABLE, PRECISION)


@dataclass
class TransferResult:
    mode: str
    target_app: str
    native: object                         # list of AE keys, or Maya native dict
    curve: TimeCurve                       # target curve in target seconds
    source_curve: TimeCurve                # mapped source curve in target seconds
    conversion: ErrorReport
    source_fidelity: Optional[ErrorReport] = None
    warnings: List[str] = field(default_factory=list)
    unreachable: list = field(default_factory=list)

    @property
    def passed(self) -> bool:
        ok = self.conversion.passed
        if self.source_fidelity is not None:
            ok = ok and self.source_fidelity.passed
        return ok

    def to_json(self) -> dict:
        return {
            "mode": self.mode,
            "target_app": self.target_app,
            "passed": self.passed,
            "warnings": self.warnings,
            "unreachable": self.unreachable,
            "conversion": self.conversion.to_json(),
            "source_fidelity": None if self.source_fidelity is None else self.source_fidelity.to_json(),
        }


def maya_to_ae(maya_native: dict, ctx: MappingContext, mode: str = EDITABLE,
               tolerance_frames: float = DEFAULT_TOLERANCE_FRAMES, target_fps=None,
               maya_samples: Optional[dict] = None, key_subdivision: int = 1) -> TransferResult:
    """Maya-native curve -> AE-native Time Remap keys.

    target_fps: AE comp frame rate (key grid for Precision mode, error unit).
    maya_samples: {"times": [frames], "values": [frames]} evaluated by Maya.
    """
    _check_mode(mode)
    report = EncodeReport()
    src_maya = maya_codec.decode(maya_native, report)
    rate = maya_native["fps"]
    fidelity = None
    if maya_samples:
        spf = FrameRate(rate).frame_duration
        times = [t * spf for t in maya_samples["times"]]
        values = [v * spf for v in maya_samples["values"]]
        fidelity = compare_samples(times, values, src_maya.evaluate, rate, tolerance_frames)
    src = ctx.maya_to_ae(src_maya)
    fps = target_fps if target_fps is not None else rate
    if mode == PRECISION:
        fit = fit_precision(src, fps, tolerance_frames, key_subdivision=key_subdivision)
        target, unreachable = fit.curve, fit.unreachable
    else:
        target, unreachable = src, []
    native = ae_codec.encode(target, report)
    emitted = ae_codec.decode(native)
    conversion = compare_curves(src, emitted, fps, tolerance_frames)
    return TransferResult(mode, "ae", native, emitted, src, conversion, fidelity,
                          report.warnings, unreachable)


def ae_to_maya(ae_keys: List[dict], ctx: MappingContext, mode: str = EDITABLE,
               tolerance_frames: float = DEFAULT_TOLERANCE_FRAMES,
               ae_samples: Optional[dict] = None, key_subdivision: int = 1) -> TransferResult:
    """AE-native Time Remap keys -> Maya-native curve dict (frames of ctx.maya_fps).

    ae_samples: {"times": [comp seconds], "values": [source seconds]} from valueAtTime.
    """
    _check_mode(mode)
    report = EncodeReport()
    src_ae = ae_codec.decode(ae_keys)
    rate = ctx.maya_fps
    fidelity = None
    if ae_samples:
        fidelity = compare_samples(ae_samples["times"], ae_samples["values"], src_ae.evaluate,
                                   rate, tolerance_frames)
    src = ctx.ae_to_maya(src_ae)
    if mode == PRECISION:
        fit = fit_precision(src, rate, tolerance_frames, key_subdivision=key_subdivision)
        target, unreachable = fit.curve, fit.unreachable
    else:
        target, unreachable = src, []
    native = maya_codec.encode(target, rate, report)
    emitted = maya_codec.decode(native)
    conversion = compare_curves(src, emitted, rate, tolerance_frames)
    return TransferResult(mode, "maya", native, emitted, src, conversion, fidelity,
                          report.warnings, unreachable)


def validate_readback(expected: TimeCurve, times: List[float], values: List[float], fps,
                      tolerance_frames: float = DEFAULT_TOLERANCE_FRAMES) -> ErrorReport:
    """Compare what the target app evaluates after apply against the expected curve.

    times/values must already be in the same seconds domain as `expected`.
    """
    return compare_samples(times, values, expected.evaluate, fps, tolerance_frames)


def _check_mode(mode: str):
    if mode not in MODES:
        raise ValueError("mode must be one of %s" % (MODES,))

