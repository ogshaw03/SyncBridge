"""Pixel Mapping Phase 3, Maya side (D-30): the AE layer's motion as keys on the link's camera.

    query = motion.query(mapping_id, start, end, origin)       -> {comp_id, ..., times} for AE
    plan = motion.plan(mapping_id, frames, reply_data)         (solves every frame, changes nothing)
    result = motion.apply(plan)                                (confirm, backup, one undo, readback)

The camera is the link's camera: the Maya layer's dedicated camera (D-29). Keys in the range are
replaced (keys outside it stay); keys are linear, one per frame. Attributes with something else than
an animation curve connected, or locked, are refused.
"""
from __future__ import annotations

import datetime
import json
import os
from typing import Dict, List, Optional

from maya import cmds

from syncbridge.core import layer_mapping as core_lm
from syncbridge.core import motion as core_motion
from syncbridge.core import pixel_mapping as core_pm

from . import layer_mapping, pixel_mapping
from .pixel_mapping import CAMERA_ATTRS

READBACK_TOLERANCE = 1e-6


def _fps():
    from .time_sync import _fps as fps
    return fps()


def _link(mapping_id: str) -> dict:
    for m in layer_mapping.stored():
        if m["id"] == mapping_id:
            return m
    raise ValueError(u"接続が見つかりません（レイヤーマップを開き直してください）。")


def query(mapping_id: str, start: float, end: float, origin: float) -> Dict[str, object]:
    """What to ask AE: the link's AE layer and the comp time of every Maya frame from start to end."""
    link = _link(mapping_id)
    frames = core_motion.frame_times(start, end, _fps(), origin)
    ae = link["ae"]
    return {"frames": [f for f, _ in frames],
            "request": {"comp_id": ae.get("comp_id"), "comp": ae.get("comp"), "layer_id": ae.get("layer_id"),
                        "layer": ae.get("layer"), "via": list(ae.get("via") or []), "times": [t for _, t in frames]}}


def record_reference(mapping_id: str, frame: float, reply: dict) -> dict:
    """Record a relative link's reference from AE at one frame (asked by Maya, for any link and the only
    way for a layer inside a precomp, D-37). The camera values of the reference are the base values
    (pixel_mapping.base_values), whatever the camera shows now (keys of an earlier transfer). One undo."""
    link = _link(mapping_id)
    if core_lm.mode_of(link) == "source":
        raise ValueError(u"素材カメラのモードは基準が要りません（素材を書き出したカメラと素材の大きさから直接合わせます）。")
    if core_lm.mode_of(link) != "relative":
        raise ValueError(u"基準を使うのは相対モードの接続だけです。")
    sample = dict(reply["samples"][0], threeD=reply["layer"].get("threeD"), parent=reply["layer"].get("parent"),
                  effects=reply["layer"].get("effects") or [])
    matrix, warnings = core_pm.ae_layer_matrix(sample)
    comp = {"width": reply["comp"]["width"], "height": reply["comp"]["height"],
            "pixelAspect": reply["comp"].get("pixelAspect", 1.0)}
    matrix, _ = core_pm.to_render_space(matrix, comp, pixel_mapping.render_data())
    values = pixel_mapping.base_values(link, link["method"])
    data = layer_mapping.store()
    updated = core_lm.with_reference(link, matrix, values, sample.get("t"))
    data["mappings"] = core_lm.upsert(data["mappings"], updated)
    cmds.undoInfo(openChunk=True, chunkName="SyncBridge record reference")
    try:
        layer_mapping.save_store(data)
    finally:
        cmds.undoInfo(closeChunk=True)
    return {"mapping": updated, "frame": frame, "warnings": warnings}


def plan(mapping_id: str, frames: List[float], reply: dict) -> Dict[str, object]:
    """Solve every frame (nothing is changed). reply = motion.result data {comp, layer, samples}."""
    link = _link(mapping_id)
    if not core_lm.has_camera(link):
        raise ValueError(u"接続「%s」の Maya レイヤーには、まだカメラが設定されていません。レイヤーマップで Maya レイヤーを選び、"
                         u"素材を書き出したカメラを設定してください。" % link["name"])
    camera = layer_mapping.node_by_uuid(link["maya"]["camera_uuid"])
    if camera is None:
        raise ValueError(u"接続「%s」のカメラ（%s）がシーンにありません。" % (link["name"], link["maya"].get("camera")))
    samples, layer = reply["samples"], reply["layer"]
    if len(samples) != len(frames):
        raise ValueError(u"AE から %d フレーム分が返りました（%d フレームを頼みました）。" % (len(samples), len(frames)))
    fixed = {"threeD": layer.get("threeD"), "parent": layer.get("parent"), "effects": layer.get("effects") or []}
    samples = [dict(s, **fixed) for s in samples]
    source_size = None
    if core_lm.mode_of(link) == "source":
        # D-39: the source camera (the dedicated camera's original) as it rendered the source, every frame
        source = pixel_mapping.source_camera(link)
        cameras = [pixel_mapping.camera_data(source, time=f) for f in frames]
        source_size = (layer["source_width"], layer["source_height"])
    else:
        cameras = [pixel_mapping.camera_data(camera, time=f) for f in frames]
    bg = None
    if core_lm.mode_of(link) == "absolute":
        bg_node = layer_mapping.node_by_uuid(link["maya"].get("bg_uuid"))
        if bg_node is None:
            raise ValueError(u"接続「%s」の BG（%s）がシーンにありません。" % (link["name"], link["maya"].get("bg")))
        bg = pixel_mapping.bg_plane_data(bg_node, layer["source_width"], layer["source_height"])
    comp = {"width": reply["comp"]["width"], "height": reply["comp"]["height"],
            "pixelAspect": reply["comp"].get("pixelAspect", 1.0)}
    solved = core_motion.solve_motion(link, samples, cameras, pixel_mapping.render_data(), comp, bg, source_size)
    keys, constant = core_motion.curves(frames, solved["values"])
    warnings = list(solved["warnings"])
    overscan = cameras[0].get("overscan", 1.0)
    if abs(float(overscan) - 1.0) > 1e-6:
        warnings.append(pixel_mapping.overscan_note(overscan))
    return {"mapping_id": mapping_id, "link": link, "camera": camera, "frames": list(frames), "keys": keys,
            "constant": constant, "max_error_px": solved["max_error_px"],
            "worst_frame": frames[solved["worst_frame"]] if frames else None, "warnings": warnings,
            "ae_layer": layer.get("name"), "comp": reply["comp"].get("name")}


def _plug(camera: str, key: str) -> str:
    return "%s.%s" % (pixel_mapping._shape(camera), CAMERA_ATTRS[key])


def problems(camera: str, keys: List[str]) -> List[str]:
    """Attributes that cannot take keys: locked, or driven by something that is not an animation curve."""
    out = []
    for key in keys:
        plug = _plug(camera, key)
        if cmds.getAttr(plug, lock=True):
            out.append(u"%s はロックされています" % plug)
            continue
        for src in cmds.listConnections(plug, source=True, destination=False) or []:
            if not cmds.objectType(src, isAType="animCurve"):
                out.append(u"%s に %s がつながっています" % (plug, src))
    return out


def existing_keys(camera: str, keys: List[str], start: float, end: float) -> Dict[str, list]:
    """{attr key: [[frame, value], ...]} of the keys that the transfer replaces (for the backup)."""
    out = {}
    for key in keys:
        plug = _plug(camera, key)
        frames = cmds.keyframe(plug, query=True, time=(start, end), timeChange=True) or []
        if frames:
            values = cmds.keyframe(plug, query=True, time=(start, end), valueChange=True) or []
            out[key] = [[f, v] for f, v in zip(frames, values)]
    return out


def _backup(p: dict, old: dict) -> str:
    from .exchange import backup_dir
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = os.path.join(backup_dir(), "motion_%s.json" % stamp)
    before = {key: cmds.getAttr(_plug(p["camera"], key)) for key in list(p["keys"]) + list(p["constant"])}
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"syncbridge": "pixel mapping motion backup", "scene": cmds.file(q=True, sn=True),
                   "camera": p["camera"], "mapping": p["link"], "range": [p["frames"][0], p["frames"][-1]],
                   "replaced_keys": old, "values_before": before}, f, indent=2, ensure_ascii=False)
    return path


def camera_label(path) -> str:
    """The camera's transform name (what the Outliner shows)."""
    parts = (path or "?").split("|")
    return parts[-2] if len(parts) > 1 and parts[-2] else parts[-1]


def describe(p: dict, old: dict) -> str:
    labels = ", ".join(CAMERA_ATTRS[k] for k in p["keys"])
    text = (u"AE のレイヤー「%s」（コンプ「%s」）の動きを、カメラ %s に %d フレーム分のキーとして打ちます"
            u"（%g〜%g フレーム、%s）。計算上の誤差は最大 %.3f px（%g フレーム）です。"
            % (p["ae_layer"], p["comp"], camera_label(p["camera"]), len(p["frames"]), p["frames"][0],
               p["frames"][-1], labels, p["max_error_px"], p["worst_frame"]))
    if old:
        text += u"\n\nこの範囲にあるキー（%s）は置き換えます（バックアップを保存します）。" % ", ".join(
            u"%s %d 個" % (CAMERA_ATTRS[k], len(v)) for k, v in old.items())
    text += u"\n元に戻すときは Ctrl+Z を 1 回。"
    return text


def describe_all(plans: List[dict], olds: List[dict], skipped: List[str]) -> str:
    """The confirmation for several links at once: one line per link."""
    lines = []
    for p, old in zip(plans, olds):
        lines.append(u"・%s → %s（%s、誤差 最大 %.3f px%s）" % (
            p["ae_layer"], camera_label(p["camera"]), ", ".join(CAMERA_ATTRS[k] for k in p["keys"]),
            p["max_error_px"], u"、範囲内のキーを置き換え" if old else u""))
    frames = plans[0]["frames"]
    text = (u"%d 本の接続の AE の動きを、%g〜%g フレーム（%d フレーム）のキーとして各カメラに打ちます。\n\n%s"
            % (len(plans), frames[0], frames[-1], len(frames), u"\n".join(lines)))
    if skipped:
        text += u"\n\n打たないもの:\n" + u"\n".join(u"・%s" % s for s in skipped)
    text += u"\n\n置き換えるキーはバックアップを保存します。元に戻すときは Ctrl+Z を 1 回（全部まとめて戻ります）。"
    return text


def apply_all(plans: List[dict], confirm: bool = True, parent=None, skipped: Optional[List[str]] = None,
              text: Optional[str] = None, backup: bool = True,
              chunk: str = "SyncBridge motion") -> List[Dict[str, object]]:
    """Key every planned camera: one confirmation, a backup per link, ONE undo chunk, readback.
    Returns a result per plan ([{"status": "cancelled"}] when the user cancels). The live sync (D-41)
    keys without asking and backs up only the first time (backup=False afterwards)."""
    for p in plans:
        trouble = problems(p["camera"], list(p["keys"]) + list(p["constant"]))
        if trouble:
            raise ValueError(u"カメラを変更していません（%s）: %s" % (p["ae_layer"], u"、".join(trouble)))
    olds = [existing_keys(p["camera"], list(p["keys"]), p["frames"][0], p["frames"][-1]) for p in plans]
    if confirm:
        from . import dialogs
        if text is None:
            text = describe(plans[0], olds[0]) if len(plans) == 1 and not skipped else \
                describe_all(plans, olds, skipped or [])
        if not dialogs.ask("SyncBridge", text, u"キーを打つ", u"キャンセル", parent):
            return [{"status": "cancelled"}]
    backups = [_backup(p, old) if backup else None for p, old in zip(plans, olds)]
    cmds.undoInfo(openChunk=True, chunkName=chunk)
    try:
        for p in plans:
            start, end = p["frames"][0], p["frames"][-1]
            for key, value in p["constant"].items():
                cmds.setAttr(_plug(p["camera"], key), value)
            for key, points in p["keys"].items():
                plug = _plug(p["camera"], key)
                cmds.cutKey(plug, time=(start, end), clear=True)
                for frame, value in points:
                    cmds.setKeyframe(plug, time=frame, value=value, inTangentType="linear", outTangentType="linear")
    finally:
        cmds.undoInfo(closeChunk=True)
    results = []
    for p, old, backup in zip(plans, olds, backups):
        worst = 0.0
        for key, points in p["keys"].items():
            plug = _plug(p["camera"], key)
            for frame, value in points:
                worst = max(worst, abs(cmds.getAttr(plug, time=frame) - value))
        results.append({"status": "applied", "camera": p["camera"], "ae_layer": p["ae_layer"],
                        "frames": [p["frames"][0], p["frames"][-1]], "count": len(p["frames"]),
                        "attrs": [CAMERA_ATTRS[k] for k in p["keys"]], "max_error_px": p["max_error_px"],
                        "readback": {"passed": worst <= READBACK_TOLERANCE, "max_diff": worst}, "backup": backup,
                        "warnings": p["warnings"], "replaced": {CAMERA_ATTRS[k]: len(v) for k, v in old.items()}})
    return results


def apply(p: dict, confirm: bool = True, parent=None) -> Dict[str, object]:
    """Key one camera as planned: confirm, backup, one undo chunk, readback."""
    return apply_all([p], confirm, parent)[0]


def transferable(store: dict):
    """(links to transfer, [reason text of each link left out]) for "transfer all"."""
    links, skipped = [], []
    for m in store["mappings"]:
        name = m["ae"].get("layer") or m.get("name")
        if not m.get("enabled", True):
            skipped.append(u"%s: 無効になっています" % name)
        elif not core_lm.has_camera(m):
            skipped.append(u"%s: Maya レイヤーのカメラがまだ設定されていません（レイヤーマップで設定してください）" % name)
        elif core_lm.mode_of(m) == "relative" and not m.get("reference"):
            skipped.append(u"%s: まだ基準がありません（AE のパネルで一度「レイヤーの初期位置を Maya へ」を送ってください）" % name)
        else:
            links.append(m)
    return links, skipped
