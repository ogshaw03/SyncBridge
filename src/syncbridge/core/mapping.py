"""Mapping between the Maya time domain and the AE time domain.

Both domains are expressed in seconds by the codecs; this module only adds
the offsets/scales that say *which* AE comp time corresponds to which Maya
scene frame, and which source time corresponds to which warped Maya frame.

    comp_time   = (maya_in_frame  - maya_input_origin_frame)  / maya_fps + ae_comp_time_offset
    source_time = ((maya_out_frame - maya_output_origin_frame) / maya_fps) * source_time_scale
                  + ae_source_time_offset

Typical pipeline (docs/SPEC.md "Time model"): Maya renders frames 1001..N
*without* the warp, the frame sequence is imported in AE (source time 0 =
frame 1001), and the AE layer reproduces the warp with Time Remap. Then
maya_input_origin_frame = maya_output_origin_frame = 1001 and the offsets
are the comp start / layer start in seconds.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .curve import TimeCurve
from .timebase import FrameRate


@dataclass
class MappingContext:
    maya_fps: list = None                    # [num, den]
    maya_input_origin_frame: float = 0.0     # Maya scene frame at comp time == ae_comp_time_offset
    maya_output_origin_frame: float = 0.0    # warped Maya frame at source time == ae_source_time_offset
    ae_comp_time_offset: float = 0.0         # seconds
    ae_source_time_offset: float = 0.0       # seconds
    source_time_scale: float = 1.0           # AE source seconds per Maya warped second

    @property
    def rate(self) -> FrameRate:
        if self.maya_fps is None:
            raise ValueError("MappingContext.maya_fps is not set")
        return FrameRate(self.maya_fps)

    def maya_to_ae(self, maya_seconds_curve: TimeCurve) -> TimeCurve:
        """Curve in Maya seconds (frame / fps) -> curve in AE comp/source seconds."""
        spf = self.rate.frame_duration
        return maya_seconds_curve.affine(
            in_scale=1.0,
            in_offset=self.ae_comp_time_offset - self.maya_input_origin_frame * spf,
            out_scale=self.source_time_scale,
            out_offset=self.ae_source_time_offset
            - self.maya_output_origin_frame * spf * self.source_time_scale,
        )

    def ae_to_maya(self, ae_curve: TimeCurve) -> TimeCurve:
        """Inverse of maya_to_ae."""
        spf = self.rate.frame_duration
        s = self.source_time_scale
        return ae_curve.affine(
            in_scale=1.0,
            in_offset=self.maya_input_origin_frame * spf - self.ae_comp_time_offset,
            out_scale=1.0 / s,
            out_offset=self.maya_output_origin_frame * spf - self.ae_source_time_offset / s,
        )

    def maya_frame_to_comp_time(self, frame: float) -> float:
        """Maya scene (input) frame -> AE comp seconds."""
        spf = self.rate.frame_duration
        return (frame - self.maya_input_origin_frame) * spf + self.ae_comp_time_offset

    def comp_time_to_maya_frame(self, comp_time: float) -> float:
        """AE comp seconds -> Maya scene (input) frame."""
        spf = self.rate.frame_duration
        return (comp_time - self.ae_comp_time_offset) / spf + self.maya_input_origin_frame

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict) -> "MappingContext":
        return cls(**d)
