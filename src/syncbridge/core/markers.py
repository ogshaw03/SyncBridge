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


# ---- markers made in Maya (D-55) -------------------------------------------------------------
# Kept as Maya frames (the keys of SB_MARKERS). For a later sync with AE they go to and come from AE comp
# markers, which sit at comp times: the same Maya frame <-> comp time as the time sync (D-22, Origin frame
# = comp 0 s), not a layer's start as the Time Remap keys above.

def maya_marker_label(index: int, count: int) -> str:
    """'マーカー 3/8' (the bookmark's name)"""
    return u"マーカー %d/%d" % (index, count)


def from_maya_frames(frames: List[float], maya_fps, origin: float) -> Dict[str, object]:
    """The markers made in Maya, with the AE comp time of each: the form a sync with AE sends."""
    from .time_sync import maya_frame_to_time
    fps = FrameRate(maya_fps)
    ordered = sorted(float(f) for f in frames)
    markers: List[dict] = []
    for index, frame in enumerate(ordered, 1):
        markers.append({"index": index, "count": len(ordered), "frame": frame,
                        "comp_time": maya_frame_to_time(frame, fps, origin),
                        "label": maya_marker_label(index, len(ordered))})
    return {"source": "maya", "maya_fps": fps.to_json(), "origin": float(origin), "markers": markers}


def maya_frames_from_comp_times(comp_times: List[float], maya_fps, origin: float) -> List[float]:
    """AE comp marker times -> the Maya frames to key on SB_MARKERS (the other way of the sync)."""
    from .time_sync import time_to_maya_frame
    return sorted(time_to_maya_frame(t, maya_fps, origin) for t in comp_times)


def marker_at(markers: List[dict], frame: float, tolerance: float = MARKER_TOLERANCE) -> Optional[dict]:
    """The marker nearest to `frame` within `tolerance` frames, or None."""
    best = None
    for marker in markers:
        distance = abs(marker["frame"] - frame)
        if distance <= tolerance and (best is None or distance < abs(best["frame"] - frame)):
            best = marker
    return best


def maya_marker_at(frames: List[float], frame: float, tolerance: float = MARKER_TOLERANCE) -> Optional[str]:
    """The label ('マーカー 3/8') of the Maya marker (D-55) at `frame`, or None: the viewport overlay's second line."""
    ordered = sorted(float(f) for f in frames)
    marker = marker_at([{"frame": f, "index": i} for i, f in enumerate(ordered, 1)], frame, tolerance)
    return None if marker is None else maya_marker_label(marker["index"], len(ordered))
