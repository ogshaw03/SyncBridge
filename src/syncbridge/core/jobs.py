"""Transfer jobs on exchange data: export data in, apply data out (pure, no I/O).

Shared by the Phase 0 CLI (files) and the Phase 1 server (WebSocket). Inputs
are the `data` parts of exchange envelopes (docs/API.md):

    maya_to_ae_job(maya export data, AE export data or None, options) -> JobResult
    ae_to_maya_job(AE export data, Maya export data or None, options) -> JobResult
    readback(apply envelope, export envelope taken after applying, tolerance) -> ErrorReport
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Optional, Tuple

from . import ae_codec, envelope, maya_codec, transfer
from .mapping import MappingContext
from .timebase import FrameRate
from .validation import DEFAULT_TOLERANCE_FRAMES, ErrorReport, compare_samples, sample_times


@dataclass
class TransferOptions:
    """User options of a transfer (CLI flags / server request fields)."""
    mode: str = transfer.EDITABLE
    tolerance_frames: float = DEFAULT_TOLERANCE_FRAMES
    origin: Optional[float] = None            # sets both Maya origins
    maya_in_origin: Optional[float] = None
    maya_out_origin: Optional[float] = None
    comp_offset: Optional[float] = None       # default: AE layer startTime, else 0
    source_offset: float = 0.0
    source_scale: float = 1.0
    key_subdivision: int = 1
    range_frames: Optional[Tuple[float, float]] = None   # Maya scene frames
    no_range: bool = False
    maya_fps: Optional[object] = None         # ae2maya without a Maya export

    def to_json(self) -> dict:
        d = asdict(self)
        if self.range_frames is not None:
            d["range_frames"] = list(self.range_frames)
        if isinstance(self.maya_fps, FrameRate):
            d["maya_fps"] = self.maya_fps.to_json()
        return d

    @classmethod
    def from_json(cls, d: Optional[dict]) -> "TransferOptions":
        d = dict(d or {})
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(d) - known)
        if unknown:
            raise ValueError("unknown transfer options: %s" % ", ".join(unknown))
        if d.get("range_frames") is not None:
            d["range_frames"] = tuple(float(x) for x in d["range_frames"])
        opts = cls(**d)
        if opts.mode not in transfer.MODES:
            raise ValueError("mode must be one of %s" % (transfer.MODES,))
        return opts


@dataclass
class JobResult:
    kind: str                      # envelope kind of `apply_data`
    apply_data: dict               # data of the apply envelope
    result: transfer.TransferResult

    @property
    def passed(self) -> bool:
        return self.result.passed

    def apply_envelope(self, source_id: str = "core") -> dict:
        return envelope.make(self.kind, self.apply_data, source_id)


def mapping_context(opts: TransferOptions, maya_fps, layer_start=None) -> MappingContext:
    origin = opts.origin if opts.origin is not None else 0.0
    comp_offset = opts.comp_offset
    if comp_offset is None:
        comp_offset = layer_start if layer_start is not None else 0.0
    return MappingContext(
        maya_fps=FrameRate(maya_fps).to_json(),
        maya_input_origin_frame=opts.maya_in_origin if opts.maya_in_origin is not None else origin,
        maya_output_origin_frame=opts.maya_out_origin if opts.maya_out_origin is not None else origin,
        ae_comp_time_offset=comp_offset,
        ae_source_time_offset=opts.source_offset,
        source_time_scale=opts.source_scale,
    )


def ae_comp_fps(ae_data: dict) -> FrameRate:
    comp = ae_data["comp"]
    return FrameRate.from_ae(comp["frameRate"], comp.get("frameDuration"))


def maya_to_ae_job(maya_data: dict, ae_data: Optional[dict], opts: TransferOptions) -> JobResult:
    native = maya_data.get("native")
    if native is None:
        raise ValueError("the Maya scene has no Scene Time Warp to send")
    target_fps = native["fps"]
    layer_start = None
    if ae_data:
        target_fps = ae_comp_fps(ae_data)
        layer_start = ae_data["layer"]["startTime"]
    ctx = mapping_context(opts, native["fps"], layer_start)
    t_range = _maya2ae_range(opts, ctx, maya_data, ae_data)
    result = transfer.maya_to_ae(native, ctx, opts.mode, opts.tolerance_frames, target_fps,
                                 maya_data.get("samples"), opts.key_subdivision, t_range)
    if ae_data:
        check_source_range(result.curve, ae_data, target_fps, ctx)
    apply_data = {
        "mode": opts.mode,
        "context": ctx.to_json(),
        "comp_fps": FrameRate(target_fps).to_json(),
        "keys": result.native,
        "report": result.to_json(),
    }
    return JobResult("ae.timeremap.apply", apply_data, result)


class SourceRangeError(ValueError):
    """The time warp needs source time outside the AE layer's source (footage / precomp)."""


def output_range(curve, fps, oversample: int = 8) -> Tuple[float, float]:
    """Min and max output time of a curve over its keys, Bezier overshoot included."""
    lo_t, hi_t = curve.domain
    values = [curve.evaluate(t) for t in sample_times(lo_t, hi_t, fps, oversample, curve.breakpoints())]
    return min(values), max(values)


def check_source_range(curve, ae_data: dict, comp_fps, ctx: MappingContext) -> None:
    """AE accepts Time Remap values only within 0 .. the layer source duration (R-16,
    confirmed on AE 26.5: setValueAtTime "value 7.26 is out of range 0 to 2").
    Refuse before anything is sent to AE, with an explanation for the user."""
    layer = ae_data.get("layer") or {}
    source = layer.get("source") or {}
    duration = source.get("duration")
    if duration is None:
        return
    duration = float(duration)
    lo, hi = output_range(curve, comp_fps)
    if lo >= -1e-6 and hi <= duration + 1e-6:
        return
    src_fps = FrameRate.from_ae(source["frameRate"]) if source.get("frameRate") else FrameRate(comp_fps)
    raise SourceRangeError(
        "AE のレイヤー「%s」の素材は %.2f 秒（%g フレーム）ですが、このタイムワープには素材の %.2f〜%.2f 秒"
        "（%g〜%g フレーム）が必要です。素材（Maya のレンダー）が短いか、原点フレーム（Origin frame = %g）が"
        "合っていません。AE には何も変更していません。"
        % (layer.get("name", "?"), duration, round(src_fps.seconds_to_frames(duration), 2), lo, hi,
           round(src_fps.seconds_to_frames(lo), 2), round(src_fps.seconds_to_frames(hi), 2),
           ctx.maya_output_origin_frame))


def ae_to_maya_job(ae_data: dict, maya_data: Optional[dict], opts: TransferOptions) -> JobResult:
    if not ae_data.get("keys"):
        layer = (ae_data.get("layer") or {}).get("name", "?")
        raise ValueError('the AE layer "%s" has no Time Remap to send '
                         "(enable Time Remap on it first)" % layer)
    maya_fps = maya_data["scene"]["fps"] if maya_data else opts.maya_fps
    if maya_fps is None:
        raise ValueError("the Maya frame rate is unknown (no Maya export and no maya_fps option)")
    ctx = mapping_context(opts, maya_fps, ae_data["layer"]["startTime"])
    t_range = _ae2maya_range(opts, ctx, ae_data, maya_data)
    result = transfer.ae_to_maya(ae_data["keys"], ctx, opts.mode, opts.tolerance_frames,
                                 ae_data.get("samples"), opts.key_subdivision, t_range)
    apply_data = {
        "mode": opts.mode,
        "context": ctx.to_json(),
        "native": result.native,
        "report": result.to_json(),
    }
    return JobResult("maya.timewarp.apply", apply_data, result)


def readback(apply_env: dict, after_env: dict,
             tolerance_frames: float = DEFAULT_TOLERANCE_FRAMES) -> ErrorReport:
    """Compare what the target app evaluates after apply (after_env samples) with what was sent."""
    data = envelope.check(apply_env)
    kind = apply_env["kind"]
    if kind == "ae.timeremap.apply":
        after = envelope.check(after_env, "ae.timeremap.export")
        expected = ae_codec.decode(data["keys"])
        fps = data["comp_fps"]
        times, values = after["samples"]["times"], after["samples"]["values"]
    elif kind == "maya.timewarp.apply":
        after = envelope.check(after_env, "maya.timewarp.export")
        expected = maya_codec.decode(data["native"])
        fps = data["native"]["fps"]
        spf = FrameRate(fps).frame_duration
        times = [t * spf for t in after["samples"]["times"]]
        values = [v * spf for v in after["samples"]["values"]]
    else:
        raise ValueError("%r is not an apply envelope" % kind)
    lo, hi = expected.domain
    pairs = [(t, v) for t, v in zip(times, values) if lo <= t <= hi]
    return compare_samples([p[0] for p in pairs], [p[1] for p in pairs],
                           expected.evaluate, fps, tolerance_frames)


# -- evaluation range (R-20) -------------------------------------------------
def _span(spans):
    spans = [s for s in spans if s is not None]
    if not spans:
        return None
    return min(s[0] for s in spans), max(s[1] for s in spans)


def _playback_frames(maya_data):
    pr = (maya_data or {}).get("scene", {}).get("playback_range")
    return (float(pr[0]), float(pr[1])) if pr else None


def _maya2ae_range(opts, ctx, maya_data, ae_data):
    """Comp-time range (seconds): range_frames, else Maya playback and AE comp ranges."""
    if opts.no_range:
        return None
    if opts.range_frames:
        return tuple(ctx.maya_frame_to_comp_time(f) for f in opts.range_frames)
    pr = _playback_frames(maya_data)
    return _span([
        tuple(ctx.maya_frame_to_comp_time(f) for f in pr) if pr else None,
        (0.0, float(ae_data["comp"]["duration"])) if ae_data else None,
    ])


def _ae2maya_range(opts, ctx, ae_data, maya_data):
    """Maya scene-time range (seconds): range_frames, else AE comp and Maya playback ranges."""
    if opts.no_range:
        return None
    spf = ctx.rate.frame_duration
    if opts.range_frames:
        return tuple(f * spf for f in opts.range_frames)
    pr = _playback_frames(maya_data)
    comp = (0.0, float(ae_data["comp"]["duration"])) if "duration" in ae_data.get("comp", {}) else None
    return _span([
        tuple(f * spf for f in pr) if pr else None,
        tuple(ctx.comp_time_to_maya_frame(t) * spf for t in comp) if comp else None,
    ])
