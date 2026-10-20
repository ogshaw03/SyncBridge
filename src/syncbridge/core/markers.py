"""AE Time Remap key timings as markers in Maya (D-18).

The keys of the selected layer's Time Remap are at comp times; they are placed on Maya
scene frames with the same mapping as a transfer (jobs.mapping_context: origin frame,
layer start), so a marker sits exactly where an AE -> Maya transfer puts the warp key.
Each marker also carries the source frame shown at that key (the Time Remap value).

Pure functions, standard library only; used by the Maya adapter (bookmarks, data stored in
the scene, viewport overlay).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from . import jobs
from .timebase import FrameRate

MARKER_TOLERANCE = 0.5      # frames: the overlay shows a marker within half a frame of its key


def _frame_text(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 1e-6:
        return "%d" % rounded
    return "%.2f" % value


def marker_label(marker: dict) -> str:
    """'AE キー 3/8  素材 36f'"""
    return u"AE キー %d/%d  素材 %sf" % (marker["index"], marker["count"], _frame_text(marker["source_frame"]))


def from_ae_export(ae_data: dict, maya_fps, options: Optional[dict] = None) -> Dict[str, object]:
    """Markers from the data of an "ae.timeremap.export" envelope.

    maya_fps: the Maya scene frame rate (FrameRate or its JSON); options: transfer options
    (origin, comp_offset, ...; see jobs.TransferOptions). Raises ValueError with a Japanese
    message when there is nothing to mark.
    """
    layer = ae_data.get("layer") or {}
    comp = ae_data.get("comp") or {}
    keys = ae_data.get("keys") or []
    if not keys:
        raise ValueError(u"レイヤー「%s」のタイムリマップにキーがありません。" % layer.get("name", ""))
    try:
        opts = jobs.TransferOptions.from_json(options)
    except (TypeError, ValueError) as exc:
        raise ValueError("options: %s" % exc)
    fps = FrameRate(maya_fps)
    ctx = jobs.mapping_context(opts, fps, layer_start=layer.get("startTime"))
    source = layer.get("source") or {}
    if source.get("frameRate"):
        source_fps = FrameRate.from_ae(source["frameRate"])
    else:
        source_fps = jobs.ae_comp_fps(ae_data)
    markers: List[dict] = []
    count = len(keys)
    for index, key in enumerate(sorted(keys, key=lambda k: k["time"]), 1):
        marker = {
            "index": index,
            "count": count,
            "comp_time": float(key["time"]),
            "frame": ctx.comp_time_to_maya_frame(float(key["time"])),
            "source_time": float(key["value"]),
            "source_frame": float(key["value"]) * float(source_fps.fraction),
        }
        marker["label"] = marker_label(marker)
        markers.append(marker)
    return {
        "comp": comp.get("name", ""),
        "layer": layer.get("name", ""),
        "maya_fps": fps.to_json(),
        "origin": ctx.maya_input_origin_frame,
        "markers": markers,
    }


def marker_at(markers: List[dict], frame: float, tolerance: float = MARKER_TOLERANCE) -> Optional[dict]:
    """The marker nearest to `frame` within `tolerance` frames, or None."""
    best = None
    for marker in markers:
        distance = abs(marker["frame"] - frame)
        if distance <= tolerance and (best is None or distance < abs(best["frame"] - frame)):
            best = marker
    return best
