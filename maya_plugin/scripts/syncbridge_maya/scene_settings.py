"""Read and change Maya scene production settings (Phase 2, D-21).

All frame values are in the current time unit. read() is what the hub compares with the AE
comp (syncbridge.core.scene_sync); apply() changes what a plan says, after the user confirms,
as one undoable step (the syncBridgeApplySettings command of the SyncBridge plug-in, H-MY-28).
Checked in mayapy 2023 / 2024: `currentUnit -updateAnimation false` keeps keys at their frame
numbers, the playback ranges keep their seconds (so they are set again), and the device aspect
ratio does not follow the pixel aspect by itself.
"""
from __future__ import annotations

import datetime
import json
import os

from maya import cmds

from syncbridge.core.timebase import FrameRate


def read() -> dict:
    unit = cmds.currentUnit(q=True, time=True)
    fps = FrameRate.from_maya_unit(unit)
    return {
        "maya_version": cmds.about(version=True),
        "time_unit": unit,
        "fps": fps.to_json(),
        "current_frame": cmds.currentTime(q=True),
        "playback_range": [cmds.playbackOptions(q=True, minTime=True),
                           cmds.playbackOptions(q=True, maxTime=True)],
        "animation_range": [cmds.playbackOptions(q=True, animationStartTime=True),
                            cmds.playbackOptions(q=True, animationEndTime=True)],
        "render_range": [cmds.getAttr("defaultRenderGlobals.startFrame"),
                         cmds.getAttr("defaultRenderGlobals.endFrame")],
        "resolution": [cmds.getAttr("defaultResolution.width"),
                       cmds.getAttr("defaultResolution.height")],
        "pixel_aspect": cmds.getAttr("defaultResolution.pixelAspect"),
        "device_aspect": cmds.getAttr("defaultResolution.deviceAspectRatio"),
    }


def _backup(settings: dict) -> str:
    from .exchange import backup_dir
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(backup_dir(), "settings_%s.json" % stamp)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"syncbridge": "maya scene settings backup", "scene": cmds.file(q=True, sn=True),
                   "settings": settings}, f, indent=2, ensure_ascii=False)
    return path


APPLY_KEYS = ("time_unit", "animation_range", "playback_range", "pixel_aspect", "device_aspect", "current_frame")


def apply(plan: dict, message: str, confirm: bool = True) -> dict:
    """Change the scene settings as `plan["apply"]` says (settings.apply.request).

    Returns {"status": "applied" | "cancelled", "backup", "after"}."""
    values = {k: v for k, v in (plan.get("apply") or {}).items() if k in APPLY_KEYS}
    if not values:
        return {"status": "unchanged", "after": read()}
    if confirm:
        from . import dialogs
        if not dialogs.ask("SyncBridge", message, u"適用", u"キャンセル"):
            print("SyncBridge: scene settings not changed (cancelled)")
            return {"status": "cancelled"}
    backup = _backup(read())
    from . import comp_guide
    comp_guide.ensure_plugin()           # the plug-in has the undoable command
    cmds.syncBridgeApplySettings(json.dumps(values))
    after = read()
    print("SyncBridge: scene settings changed (backup: %s)" % backup)
    return {"status": "applied", "backup": backup, "after": after}
