"""Pixel Mapping Phase 3 (D-30): an AE layer's motion as keys on the linked Maya camera.

The AE layer is sampled at every Maya frame of a range (AE comp time t = (frame - origin) / fps, the
same Origin frame as the time slider sync), each sample is solved like a single send
(core.pixel_mapping.solve / solve_relative) and the results become one key per frame.

    frames = frame_times(1001, 1096, FrameRate(24), origin=1001)      -> [(1001.0, 0.0), ...]
    result = solve_motion(link, samples, cameras, render, comp, bg)    (one camera dict per frame)
    keys, constant = curves([f for f, _ in frames], result["values"])

Pure functions, standard library only.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from . import pixel_mapping as pm
from .layer_mapping import mode_of
from .time_sync import maya_frame_to_time

MAX_FRAMES = 10000


def frame_times(start: float, end: float, maya_fps, origin: float) -> List[Tuple[float, float]]:
    """[(Maya frame, AE comp time)] for every whole frame from start to end (both included)."""
    first, last = int(round(start)), int(round(end))
    if last < first:
        raise ValueError(u"終了フレームは開始フレームより後にしてください。")
    if last - first + 1 > MAX_FRAMES:
        raise ValueError(u"一度に送れるのは %d フレームまでです。" % MAX_FRAMES)
    return [(float(f), maya_frame_to_time(f, maya_fps, origin)) for f in range(first, last + 1)]


def solve_motion(link: dict, samples: Sequence[dict], cameras: Sequence[dict], render: dict, comp: dict,
                 bg: Optional[dict] = None, source_size: Optional[Sequence[float]] = None) -> Dict[str, object]:
    """Camera values for every sample (an AE layer transform, as SBCep.layerMotion() gives it) with the
    camera at the same frame (pixel_mapping.camera_data at that frame).

    Relative links need their reference (recorded by a first single send). Source camera links (D-39)
    need the AE layer's source size, and `cameras` are the source camera's (the Maya layer's camera, as
    it rendered the source). Returns {values: [dict per frame], max_error_px, worst_frame (index),
    warnings}. ValueError (Japanese) naming the first frame that cannot be shown."""
    if len(samples) != len(cameras):
        raise ValueError("samples and cameras differ in length")
    mode, method = mode_of(link), link["method"]
    ref = link.get("reference")
    if mode == "relative" and not ref:
        raise ValueError(u"接続「%s」にはまだ基準がありません。Maya と AE の見え方を合わせ、AE のパネルで一度"
                         u"「レイヤーの初期位置を Maya へ」を送って基準を記録してから、アニメーションを転送してください。"
                         % link.get("name", ""))
    if mode == "absolute" and bg is None:
        raise ValueError("absolute mode needs the BG plane")
    if mode == "source" and not source_size:
        raise ValueError("source camera mode needs the source size")
    values, warnings, worst, worst_i = [], [], 0.0, 0
    for i, (sample, camera) in enumerate(zip(samples, cameras)):
        try:
            matrix, more = pm.ae_layer_matrix(sample)
            if mode == "source":
                solved = pm.solve_source(method, camera, render, source_size, matrix, comp)
                values.append(solved["values"])
                for w in more + list(solved.get("warnings") or []):
                    if w not in warnings:
                        warnings.append(w)
                if solved["max_error_px"] > worst:
                    worst, worst_i = solved["max_error_px"], i
                continue
            matrix, in_render = pm.to_render_space(matrix, comp, render)     # a render with a margin (D-36)
            if mode == "relative":
                solved = pm.solve_relative(method, dict(camera, **ref["camera"]), render, in_render, ref["matrix"],
                                           matrix)
            else:
                solved = pm.solve(method, camera, render, bg, matrix, in_render)
        except ValueError as exc:
            raise ValueError(u"AE の %.3f 秒（%d フレーム目）: %s" % (float(sample.get("t", 0.0)), i + 1, exc))
        values.append(solved["values"])
        for w in more + list(solved.get("warnings") or []):
            if w not in warnings:
                warnings.append(w)
        if solved["max_error_px"] > worst:
            worst, worst_i = solved["max_error_px"], i
    return {"values": values, "max_error_px": worst, "worst_frame": worst_i, "warnings": warnings}


def curves(frames: Sequence[float], values: Sequence[dict]) -> Tuple[Dict[str, List[Tuple[float, float]]],
                                                                     Dict[str, object]]:
    """({attr key: [(frame, value)]} to key, {attr key: value} to set once): switches (bool) are set,
    not keyed; a number is keyed even when it does not change (so the whole range is held by keys)."""
    keys: Dict[str, List[Tuple[float, float]]] = {}
    constant: Dict[str, object] = {}
    for frame, vals in zip(frames, values):
        for key, value in vals.items():
            if isinstance(value, bool):
                if constant.get(key, value) != value:
                    raise ValueError("switch %s changes inside the range" % key)
                constant[key] = value
            else:
                keys.setdefault(key, []).append((float(frame), float(value)))
    return keys, constant
