"""Phase 0 file-based transfer for the Maya Scene Time Warp.

    export_timewarp(path)  -> writes kind "maya.timewarp.export"
    apply_timewarp(path)   -> reads  kind "maya.timewarp.apply" (from the CLI)

apply_timewarp asks for confirmation, writes a JSON backup of the current
curve, applies inside one undo chunk, then reads the curve back and checks
that Maya evaluates what was sent (readback).
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


def build_export(oversample: int = 4) -> dict:
    curve, plug = scene_timewarp.find_curve()
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


def apply_timewarp(path: str = None, confirm: bool = True) -> dict:
    if path is None:
        picked = cmds.fileDialog2(fileFilter="JSON (*.json)", dialogStyle=2, fileMode=1,
                                  caption="SyncBridge: apply Scene Time Warp")
        if not picked:
            return None
        path = picked[0]
    data = envelope.load(path, "maya.timewarp.apply")["data"]
    native = data["native"]
    curve, _ = scene_timewarp.find_curve()

    if confirm:
        answer = cmds.confirmDialog(
            title="SyncBridge",
            message="Replace the keys of Scene Time Warp curve '%s' with %d keys (%s mode)?\n"
                    "A JSON backup is written first." % (curve, len(native["keys"]), data["mode"]),
            button=["Apply", "Cancel"], defaultButton="Apply", cancelButton="Cancel",
            dismissString="Cancel")
        if answer != "Apply":
            return None

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir(), "timewarp_%s.json" % stamp)
    envelope.save(backup_path, build_export())

    cmds.undoInfo(openChunk=True, chunkName="SyncBridge apply time warp")
    try:
        anim_curve.write_curve(curve, native)
    finally:
        cmds.undoInfo(closeChunk=True)

    # Readback: does Maya evaluate what we intended?
    _, samples, _ = anim_curve.read_curve(curve)
    expected = maya_codec.decode(native)
    spf = 1.0 / anim_curve.scene_fps().fps
    report = validate_readback(expected, [t * spf for t in samples["times"]],
                               [v * spf for v in samples["values"]], native["fps"])
    print("SyncBridge: applied %s (backup: %s)" % (path, backup_path))
    print("SyncBridge: readback", report.summary())
    return {"backup": backup_path, "readback": report.to_json()}
