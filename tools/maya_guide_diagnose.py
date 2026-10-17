"""Diagnose the comp guide (D-16) in an interactive Maya session. Run in the Script Editor (Python):

    REPO = r"<repository folder>"
    exec(open(REPO + r"/tools/maya_guide_diagnose.py", encoding="utf-8").read())

Prints the views, their cameras and renderers, what Maya reports as the active view
(H-MY-21), then reloads the guide plug-in from the repository and shows a test frame on
the camera of the active view (H-MY-19). Look at that view: is an orange frame drawn?
Changes nothing but the guide (which is never saved, D-16).
"""
import os
import sys

from maya import cmds
import maya.api.OpenMayaUI as omui

_REPO = globals().get("REPO")
if not _REPO or not os.path.isdir(_REPO):
    raise RuntimeError("set REPO to the SyncBridge repository folder first")
for _p in (os.path.join(_REPO, "maya_plugin", "scripts"), os.path.join(_REPO, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _line(*parts):
    print("[SyncBridge guide] " + " ".join(str(p) for p in parts))


_line("Maya", cmds.about(version=True))
visible = cmds.getPanel(visiblePanels=True) or []
for panel in cmds.getPanel(type="modelPanel") or []:
    try:
        _line("panel", panel, "camera=%s" % cmds.modelEditor(panel, q=True, camera=True),
              "renderer=%s" % cmds.modelEditor(panel, q=True, rendererName=True),
              "locators=%s" % cmds.modelEditor(panel, q=True, locators=True),
              "visible" if panel in visible else "hidden")
    except RuntimeError as exc:
        _line("panel", panel, "error", exc)
try:
    _line("playblast -activeEditor:", cmds.playblast(activeEditor=True))
except RuntimeError as exc:
    _line("playblast -activeEditor failed:", exc)
_line("getPanel -withFocus:", cmds.getPanel(withFocus=True))
try:
    _line("M3dView.active3dView camera:", omui.M3dView.active3dView().getCamera().fullPathName())
except Exception as exc:
    _line("M3dView.active3dView failed:", exc)
_line("guides before:", cmds.ls(type="syncBridgeCompGuide", long=True) if cmds.pluginInfo(
    "syncbridge_guide.py", q=True, loaded=True) else "(plug-in not loaded)")

# Reload the plug-in from the repository (the fixed version) and draw a test frame.
from syncbridge_maya import comp_guide as _guide
if cmds.pluginInfo(_guide.PLUGIN_FILE, q=True, loaded=True):
    _guide.clear()
    cmds.unloadPlugin(_guide.PLUGIN_FILE, force=True)
_plugin = os.path.join(_REPO, "maya_plugin", "plug-ins", _guide.PLUGIN_FILE)
try:
    cmds.loadPlugin(_plugin)
except RuntimeError as _exc:
    _line("loading the plug-in failed (see the lines above). Restart Maya and run this again. (%s)" % _exc)
    raise
_line("plug-in loaded from:", cmds.pluginInfo(_guide.PLUGIN_FILE, q=True, path=True))
_camera = omui.M3dView.active3dView().getCamera().fullPathName()   # show() accepts the shape
_result = _guide.show({"name": "diagnose", "width": 1280, "height": 720}, camera=_camera)
_line("test frame:", _result)
for _shape in _guide.existing():
    _xf = cmds.listRelatives(_shape, parent=True, fullPath=True)[0]
    _cam = _guide.guide_camera(_shape)
    _line("guide", _shape, "visibility=%s/%s" % (cmds.getAttr(_shape + ".visibility"), cmds.getAttr(_xf + ".visibility")),
          "linked camera=%s" % _cam,
          "camera position=%s" % ([round(v, 3) for v in cmds.xform(_cam, q=True, worldSpace=True, translation=True)]
                                  if _cam else None),
          "guide bounding box=%s" % [round(v, 3) for v in cmds.exactWorldBoundingBox(_shape)])

# Redraw with the plug-in's debug output on (H-MY-19): which drawing steps run, and why nothing shows.
# It stays on (first 3 calls of each step) so a normal redraw, e.g. after orbiting the view, prints too.
os.environ["SYNCBRIDGE_GUIDE_DEBUG"] = "1"
cmds.refresh(force=True)
cmds.refresh(force=True)
_line("Look at the view of camera", _result["camera"], ": is an orange frame with 'AE diagnose 1280x720' drawn?")
_line("Now move the view a little (Alt + drag) and copy the '[SyncBridge guide debug]' lines that follow.")
_line("Debug output stays on until Maya is restarted.")
