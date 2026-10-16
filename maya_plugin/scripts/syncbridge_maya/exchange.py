"""Export / apply of the Maya Scene Time Warp.

Phase 0 (files):
    export_timewarp(path)  -> writes kind "maya.timewarp.export"
    apply_timewarp(path)   -> reads  kind "maya.timewarp.apply" (from the CLI)
Phase 1 (server, see service.py):
    build_export(allow_missing=True) and apply_envelope(env) on the received data

Applying asks for confirmation, writes a JSON backup of the current curve,
applies inside one undo chunk, then reads the curve back and checks that Maya
evaluates what was sent (readback). Must run on Maya's main thread.
"""
from __future__ import annotations

import datetime
import os

from maya import cmds

from syncbridge.core import envelope, maya_codec
from syncbridge.core.transfer import validate_readback
from . import anim_curve, scene_settings, scene_timewarp

SOURCE_ID = "maya"


def _app_info() -> dict:
    return {"name": "maya", "version": cmds.about(version=True), "scene": cmds.file(q=True, sn=True)}


def build_export(oversample: int = 4, allow_missing: bool = False) -> dict:
    """Export envelope of the Scene Time Warp.

    allow_missing: without a Scene Time Warp curve, return the scene settings
    with native = None instead of raising (the server needs the fps and the
    playback range to convert AE -> Maya).
    """
    try:
        curve, plug = scene_timewarp.find_curve()
    except scene_timewarp.SceneTimeWarpNotFound:
        if not allow_missing:
            raise
        return envelope.make("maya.timewarp.export", {
            "curve_node": None, "time_plug": None, "enabled": scene_timewarp.is_enabled(),
            "native": None, "samples": None, "calibration": None, "scene": scene_settings.read(),
        }, SOURCE_ID, _app_info())
    native, samples, calibration = anim_curve.read_curve(curve, oversample)
    return envelope.make("maya.timewarp.export", {
        "curve_node": curve,
        "time_plug": plug,
        "enabled": scene_timewarp.is_enabled(),
        "native": native,
        "samples": samples,
        "calibration": calibration,
        "scene": scene_settings.read(),
    }, SOURCE_ID, _app_info())


def export_timewarp(path: str = None, oversample: int = 4) -> str:
    if path is None:
        picked = cmds.fileDialog2(fileFilter="JSON (*.json)", dialogStyle=2, fileMode=0,
                                  caption="SyncBridge: export Scene Time Warp")
        if not picked:
            return None
        path = picked[0]
    env = build_export(oversample)
    envelope.save(path, env)
    report = env["data"]["calibration"]["decode_vs_maya"]
    print("SyncBridge: exported %d keys to %s (decode vs Maya max %.5f f, %s)"
          % (len(env["data"]["native"]["keys"]), path, report["max_error_frames"],
             "PASS" if report["passed"] else "FAIL"))
    for w in env["data"]["native"].get("warnings", []):
        cmds.warning("SyncBridge: " + w)
    return path


def backup_dir() -> str:
    d = os.path.join(cmds.internalVar(userAppDir=True), "SyncBridge", "backups")
    if not os.path.isdir(d):
        os.makedirs(d)
    return d


def apply_envelope(apply_env: dict, confirm: bool = True, origin: str = "") -> dict:
    """Apply a "maya.timewarp.apply" envelope to the Scene Time Warp.

    Returns {"status": "applied" | "cancelled", "backup", "after", "app_readback", "message"}.
    `after` is an export taken after applying (the server checks it, SPEC 5).
    """
    data = envelope.check(apply_env, "maya.timewarp.apply")
    native = data["native"]
    try:
        curve, _ = scene_timewarp.find_curve()
    except scene_timewarp.SceneTimeWarpNotFound:
        raise RuntimeError(u"このシーンには Scene Time Warp がありません。"
                           u"先に Scene Time Warp を作成してから、もう一度実行してください。")

    if confirm:
        source = (u"%s の " % origin) if origin else u""
        answer = cmds.confirmDialog(
            title="SyncBridge",
            message=u"Scene Time Warp「%s」のキーを、%s%d キーで置き換えますか？\n"
                    u"先にバックアップを保存します。元に戻すときは取り消し（Ctrl+Z）を 1 回押してください。"
                    % (curve, source, len(native["keys"])),
            button=[u"適用", u"キャンセル"], defaultButton=u"適用", cancelButton=u"キャンセル",
            dismissString=u"キャンセル")
        if answer != u"適用":
            print("SyncBridge: apply cancelled")
            return {"status": "cancelled"}

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir(), "timewarp_%s.json" % stamp)
    envelope.save(backup_path, build_export())

    cmds.undoInfo(openChunk=True, chunkName="SyncBridge apply time warp")
    try:
        anim_curve.write_curve(curve, native)
    finally:
        cmds.undoInfo(closeChunk=True)

    # Readback: does Maya evaluate what we intended?
    after = build_export()
    samples = after["data"]["samples"]
    expected = maya_codec.decode(native)
    spf = 1.0 / anim_curve.scene_fps().fps
    report = validate_readback(expected, [t * spf for t in samples["times"]],
                               [v * spf for v in samples["values"]], native["fps"])
    print("SyncBridge: applied %d keys (backup: %s)" % (len(native["keys"]), backup_path))
    print("SyncBridge: readback", report.summary())
    return {"status": "applied", "backup": backup_path, "after": after,
            "app_readback": report.to_json()}


def apply_timewarp(path: str = None, confirm: bool = True) -> dict:
    """Phase 0: apply an apply file written by the CLI (ae2maya)."""
    if path is None:
        picked = cmds.fileDialog2(fileFilter="JSON (*.json)", dialogStyle=2, fileMode=1,
                                  caption="SyncBridge: apply Scene Time Warp")
        if not picked:
            return None
        path = picked[0]
    return apply_envelope(envelope.load(path, "maya.timewarp.apply"), confirm)
