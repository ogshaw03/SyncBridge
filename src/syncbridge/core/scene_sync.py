"""Scene settings transfer between Maya and the active AE comp (Phase 2, D-21).

Items: FPS, playback range, animation range, pixel aspect ratio. Time mapping is the one of
a transfer (jobs.mapping_context without a layer): Maya frame F <-> AE comp time
(F - origin) / Maya fps. The AE comp's start frame (displayStartTime) is set to the origin
frame so that AE shows the same frame numbers as Maya.

    Maya animation range [ast, aet]  <->  AE comp: starts at the origin, duration aet - origin + 1
    Maya playback range [min, max]   <->  AE work area
    Maya FPS (currentUnit -time)     <->  comp.frameRate (Maya keeps keys at their frames)
    defaultResolution.pixelAspect    <->  comp.pixelAspect

Pure functions, standard library only. Inputs are the settings each app reports:

    maya: syncbridge_maya.scene_settings.read()  {fps, time_unit, playback_range, animation_range,
          pixel_aspect, resolution, current_frame, ...}
    ae:   SBCep.sceneSettings()  {comp, frameRate, frameDuration, duration, displayStartTime,
          workAreaStart, workAreaDuration, pixelAspect, width, height, time}

A plan is {direction, origin, items, apply, changes, warnings}; `apply` holds only the values to
change, in the target app's terms. Errors for the user are ValueError with a Japanese message.
"""
from __future__ import annotations

from typing import Iterable, List, Optional

from .timebase import FrameRate

ITEMS = ("fps", "playback_range", "animation_range", "pixel_aspect")
ITEM_LABELS = {
    "fps": u"FPS",
    "playback_range": u"再生範囲",
    "animation_range": u"アニメーション範囲",
    "pixel_aspect": u"ピクセル縦横比",
}

# Maya time units that can be set with `currentUnit -time` (mayapy 2023 / 2024, 2026-10-20).
# 72fps and 18fps were refused; 119.88fps only exists from Maya 2024, so it is left out.
MAYA_TIME_UNIT_NAMES = (
    "game", "film", "pal", "ntsc", "show", "palf", "ntscf",
    "23.976fps", "29.97fps", "47.952fps", "59.94fps",
    "8fps", "10fps", "12fps", "16fps", "20fps", "75fps", "80fps", "90fps", "100fps", "120fps", "240fps",
)

RATE_TOLERANCE = 0.01        # fps: AE's 29.97 (2997/100) and Maya's 29.97fps are the same rate
TIME_TOLERANCE = 1e-4        # seconds
FRAME_TOLERANCE = 1e-3       # frames
ASPECT_TOLERANCE = 1e-4


# -- frame rates ------------------------------------------------------------------
def same_rate(a, b) -> bool:
    return abs(FrameRate(a).fps - FrameRate(b).fps) < RATE_TOLERANCE


def rate_text(rate) -> str:
    """'24', '23.976', '29.97'"""
    return "%g" % round(FrameRate(rate).fps, 3)


def maya_unit_for(rate) -> str:
    """The Maya time unit for a frame rate (ValueError when Maya has none)."""
    best = None
    for name in MAYA_TIME_UNIT_NAMES:
        diff = abs(FrameRate.from_maya_unit(name).fps - FrameRate(rate).fps)
        if diff < RATE_TOLERANCE and (best is None or diff < best[0]):
            best = (diff, name)
    if best is None:
        raise ValueError(u"Maya はこの FPS（%s）に対応していません。AE のコンプのフレームレートを変えるか、"
                         u"FPS を送る項目から外してください。" % rate_text(rate))
    return best[1]


def ae_rate(ae: dict) -> FrameRate:
    return FrameRate.from_ae(ae["frameRate"], ae.get("frameDuration"))


# -- helpers -------------------------------------------------------------------------
def _frame_text(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < FRAME_TOLERANCE:
        return "%d" % rounded
    return "%.2f" % value


def _range_text(first: float, last: float) -> str:
    return u"%s〜%s" % (_frame_text(first), _frame_text(last))


def _snap(value: float) -> float:
    rounded = round(value)
    return float(rounded) if abs(value - rounded) < FRAME_TOLERANCE else value


def _check_items(items: Optional[Iterable[str]]) -> List[str]:
    chosen = list(ITEMS) if items is None else [i for i in ITEMS if i in set(items)]
    unknown = sorted(set(items or ()) - set(ITEMS))
    if unknown:
        raise ValueError("unknown settings items: %s" % ", ".join(unknown))
    if not chosen:
        raise ValueError(u"送る項目を 1 つ以上選んでください。")
    return chosen


def _change(item: str, before: str, after: str) -> dict:
    return {"item": item, "label": ITEM_LABELS[item], "before": before, "after": after}


def _add_change(changes: List[dict], item: str, before: str, after: str) -> None:
    """Listed for the user only when it looks different (a range is set again after an FPS
    change even when its frame numbers stay the same)."""
    if before != after:
        changes.append(_change(item, before, after))


def _plan(direction: str, origin: float, items: List[str]) -> dict:
    return {"direction": direction, "origin": origin, "items": items, "apply": {}, "changes": [],
            "warnings": []}


# -- Maya -> AE -----------------------------------------------------------------------
def maya_to_ae(maya: dict, ae: dict, items: Optional[Iterable[str]] = None, origin: float = 1.0) -> dict:
    """Plan to change the active AE comp from the Maya scene settings."""
    items = _check_items(items)
    origin = float(origin)
    plan = _plan("maya2ae", origin, items)
    apply, changes, warnings = plan["apply"], plan["changes"], plan["warnings"]
    r_maya = FrameRate(maya["fps"])
    r_ae_old = ae_rate(ae)
    r_ae = r_ae_old

    if "fps" in items and not same_rate(r_maya, r_ae_old):
        apply["frameRate"] = r_maya.fps
        changes.append(_change("fps", rate_text(r_ae_old), rate_text(r_maya)))
        r_ae = r_maya

    def comp_time(frame: float) -> float:
        return (float(frame) - origin) / r_maya.fps

    duration = float(ae["duration"])
    old_start = float(ae.get("displayStartTime") or 0.0) * r_ae_old.fps
    old_frames = duration * r_ae_old.fps
    if "animation_range" in items:
        ast, aet = (float(v) for v in maya["animation_range"])
        if aet < origin:
            raise ValueError(u"Maya のアニメーション範囲の終わり（%s）が Origin frame（%s）より前です。"
                             u"AE のコンプは Origin frame から始まります。"
                             % (_frame_text(aet), _frame_text(origin)))
        if abs(ast - origin) > FRAME_TOLERANCE:
            warnings.append(u"AE のコンプは Origin frame（%s）から始まります。Maya のアニメーション範囲の始め（%s）"
                            u"とは合いません。" % (_frame_text(origin), _frame_text(ast)))
        new_duration = comp_time(aet) + 1.0 / r_maya.fps
        new_display_start = origin / r_ae.fps
        frames = new_duration * r_ae.fps
        if abs(frames - round(frames)) > FRAME_TOLERANCE:
            warnings.append(u"AE のコンプの長さが %.2f フレームになります（FPS が Maya と違うため）。" % frames)
        if abs(new_duration - duration) > TIME_TOLERANCE or "frameRate" in apply:
            apply["duration"] = new_duration
            duration = new_duration
        if abs(new_display_start * r_ae.fps - old_start) > FRAME_TOLERANCE or "frameRate" in apply:
            apply["displayStartTime"] = new_display_start
        if "duration" in apply or "displayStartTime" in apply:
            _add_change(changes, "animation_range", _range_text(old_start, old_start + old_frames - 1),
                        _range_text(origin, origin + frames - 1))

    if "playback_range" in items:
        lo, hi = (float(v) for v in maya["playback_range"])
        start, end = comp_time(lo), comp_time(hi) + 1.0 / r_maya.fps
        if start < -TIME_TOLERANCE or end > duration + TIME_TOLERANCE:
            warnings.append(u"Maya の再生範囲（%s）が AE のコンプからはみ出すため、コンプの中に収めました。"
                            % _range_text(lo, hi))
            start, end = max(start, 0.0), min(end, duration)
        if end - start <= TIME_TOLERANCE:
            warnings.append(u"Maya の再生範囲が AE のコンプの外にあるため、ワークエリアは変えていません。")
        else:
            old_ws, old_wd = float(ae["workAreaStart"]), float(ae["workAreaDuration"])
            if (abs(start - old_ws) > TIME_TOLERANCE or abs(end - start - old_wd) > TIME_TOLERANCE
                    or "frameRate" in apply):
                apply["workAreaStart"] = start
                apply["workAreaDuration"] = end - start
                before_first = old_start + old_ws * r_ae_old.fps
                after_first = origin + start * r_maya.fps
                _add_change(changes, "playback_range",
                            _range_text(before_first, before_first + old_wd * r_ae_old.fps - 1),
                            _range_text(after_first, after_first + (end - start) * r_maya.fps - 1))

    if "pixel_aspect" in items:
        pa = float(maya["pixel_aspect"])
        if abs(pa - float(ae["pixelAspect"])) > ASPECT_TOLERANCE:
            apply["pixelAspect"] = pa
            changes.append(_change("pixel_aspect", "%g" % float(ae["pixelAspect"]), "%g" % pa))
    return plan


# -- AE -> Maya -----------------------------------------------------------------------
def ae_to_maya(ae: dict, maya: dict, items: Optional[Iterable[str]] = None, origin: float = 1.0) -> dict:
    """Plan to change the Maya scene settings from the active AE comp."""
    items = _check_items(items)
    origin = float(origin)
    plan = _plan("ae2maya", origin, items)
    apply, changes, warnings = plan["apply"], plan["changes"], plan["warnings"]
    r_ae = ae_rate(ae)
    r_maya_old = FrameRate(maya["fps"])
    r_maya = r_maya_old

    if "fps" in items and not same_rate(r_ae, r_maya_old):
        unit = maya_unit_for(r_ae)
        r_maya = FrameRate.from_maya_unit(unit)
        apply["time_unit"] = unit
        apply["current_frame"] = float(maya["current_frame"])     # keys and the time stay at their frames
        changes.append(_change("fps", rate_text(r_maya_old), rate_text(r_maya)))

    def maya_frame(comp_time: float) -> float:
        return _snap(origin + float(comp_time) * r_maya.fps)

    display_start = float(ae.get("displayStartTime") or 0.0) * r_ae.fps
    ae_frames = float(ae["duration"]) * r_ae.fps
    if abs(ae_frames - round(ae_frames)) > FRAME_TOLERANCE:
        warnings.append(u"AE のコンプの長さが %.2f フレームで、フレームの区切りではありません。" % ae_frames)

    if "animation_range" in items:
        if abs(display_start - origin) > FRAME_TOLERANCE:
            warnings.append(u"AE のコンプの開始フレーム（%s）が Origin frame（%s）と違います。"
                            u"Maya では Origin frame から始まる範囲にしました。"
                            % (_frame_text(display_start), _frame_text(origin)))
        new_range = [_snap(origin), maya_frame(float(ae["duration"])) - 1.0]
        old_range = [float(v) for v in maya["animation_range"]]
        if (any(abs(a - b) > FRAME_TOLERANCE for a, b in zip(new_range, old_range))
                or "time_unit" in apply):
            apply["animation_range"] = new_range
            _add_change(changes, "animation_range", _range_text(*old_range), _range_text(*new_range))

    if "playback_range" in items:
        first = maya_frame(float(ae["workAreaStart"]))
        last = maya_frame(float(ae["workAreaStart"]) + float(ae["workAreaDuration"])) - 1.0
        new_range = [first, last]
        old_range = [float(v) for v in maya["playback_range"]]
        if (any(abs(a - b) > FRAME_TOLERANCE for a, b in zip(new_range, old_range))
                or "time_unit" in apply):
            apply["playback_range"] = new_range
            _add_change(changes, "playback_range", _range_text(*old_range), _range_text(*new_range))

    if "pixel_aspect" in items:
        pa = float(ae["pixelAspect"])
        if abs(pa - float(maya["pixel_aspect"])) > ASPECT_TOLERANCE:
            width, height = (float(v) for v in maya["resolution"])
            apply["pixel_aspect"] = pa
            # Maya does not update the device aspect ratio by itself (mayapy 2023 / 2024).
            apply["device_aspect"] = width / height * pa
            changes.append(_change("pixel_aspect", "%g" % float(maya["pixel_aspect"]), "%g" % pa))
    return plan


def make_plan(direction: str, source: dict, target: dict, items=None, origin: float = 1.0) -> dict:
    if direction == "maya2ae":
        return maya_to_ae(source, target, items, origin)
    if direction == "ae2maya":
        return ae_to_maya(source, target, items, origin)
    raise ValueError("direction must be maya2ae or ae2maya")


# -- confirmation and readback ---------------------------------------------------------
def confirm_text(plan: dict, source_label: str) -> str:
    """Question for the confirmation dialog in the target app."""
    target = u"この AE のコンプ" if plan["direction"] == "maya2ae" else u"この Maya のシーン"
    lines = [u"%sの設定を、%sに適用しますか？" % (source_label, target), u""]
    for c in plan["changes"]:
        lines.append(u"%s: %s → %s" % (c["label"], c["before"], c["after"]))
    if plan["direction"] == "ae2maya" and "time_unit" in plan["apply"]:
        lines.append(u"（FPS を変えても、キーはフレーム番号のまま動きません）")
    for w in plan["warnings"]:
        lines += [u"", u"注意: " + w]
    lines += [u"", u"先にバックアップを保存します。元に戻すときは取り消し（Ctrl+Z）を 1 回押してください。"]
    return u"\n".join(lines)


def check_after(plan: dict, after: dict) -> List[dict]:
    """Values that the target app does not report as planned: [{key, expected, actual}]."""
    problems: List[dict] = []

    def compare(key, expected, actual, tolerance):
        if abs(float(expected) - float(actual)) > tolerance:
            problems.append({"key": key, "expected": expected, "actual": actual})

    apply = plan["apply"]
    if plan["direction"] == "maya2ae":
        if "frameRate" in apply and not same_rate(apply["frameRate"], ae_rate(after)):
            problems.append({"key": "frameRate", "expected": apply["frameRate"], "actual": after["frameRate"]})
        for key in ("duration", "displayStartTime", "workAreaStart", "workAreaDuration"):
            if key in apply:
                compare(key, apply[key], after[key], TIME_TOLERANCE)
        if "pixelAspect" in apply:
            compare("pixelAspect", apply["pixelAspect"], after["pixelAspect"], ASPECT_TOLERANCE)
    else:
        if "time_unit" in apply and not same_rate(FrameRate.from_maya_unit(apply["time_unit"]), after["fps"]):
            problems.append({"key": "time_unit", "expected": apply["time_unit"], "actual": after.get("time_unit")})
        for key in ("animation_range", "playback_range"):
            if key in apply:
                for e, a in zip(apply[key], after[key]):
                    compare(key, e, a, FRAME_TOLERANCE)
        if "pixel_aspect" in apply:
            compare("pixel_aspect", apply["pixel_aspect"], after["pixel_aspect"], ASPECT_TOLERANCE)
    return problems


def describe(plan: dict) -> str:
    """One line for logs: 'FPS 24 → 30, 再生範囲 1〜48 → 1〜60'."""
    if not plan["changes"]:
        return u"変更なし"
    return u", ".join(u"%s %s → %s" % (c["label"], c["before"], c["after"]) for c in plan["changes"])


__all__ = ["ITEMS", "ITEM_LABELS", "maya_to_ae", "ae_to_maya", "make_plan", "confirm_text", "check_after",
           "describe", "maya_unit_for", "same_rate", "rate_text"]
