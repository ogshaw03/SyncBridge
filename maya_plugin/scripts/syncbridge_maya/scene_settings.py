"""Read Maya scene production settings (Phase 2 will add writing).

All frame values are in the current time unit. Commands/attributes used are
documented (playbackOptions, currentUnit, defaultRenderGlobals,
defaultResolution) but not yet run on Maya by this project.
"""
from __future__ import annotations

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
