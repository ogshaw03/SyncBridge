"""mayapy: the delivery cleanup (D-47).

    mayapy tools/maya_cleanup_check.py <out folder>

Run with MAYA_APP_DIR set to a scratch folder (the backup goes to its SyncBridge/backups).
1. A scene with every node SyncBridge makes (a Maya layer and its dedicated camera with keys, key
   markers, the Origin frame, the comp guide, the key marker overlay, the viewer camera), a bookmark
   of the user's and a Scene Time Warp.
2. Keep the cameras: they lose the mark and the locks, keep their keys and the link to the original;
   everything else of ours is gone, the time warp and the user's bookmark stay. One undo restores.
3. Delete the cameras (after removing the user's bookmark): the saved file has no node of ours and
   no `requires` but Maya's. One undo restores.
Prints "OK" / "NG" per check and "RESULT PASS" / "RESULT FAIL".
"""
import os
import re
import sys

import maya.standalone
maya.standalone.initialize()
import maya.cmds as cmds  # noqa: E402

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path[:0] = [os.path.join(REPO, "src"), os.path.join(REPO, "maya_plugin", "scripts")]
from syncbridge_maya import (cleanup, comp_guide, key_markers, layer_camera, layer_mapping,  # noqa: E402
                             timing, viewer_camera)

OUT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
os.makedirs(OUT, exist_ok=True)
checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print("%s  %s  %s" % ("OK" if ok else "NG", name, detail))


def saved(name):
    path = os.path.join(OUT, name)
    cmds.file(rename=path)
    cmds.file(save=True, type="mayaAscii", force=True)
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    return (re.findall(r"^requires [^\n]*", text, re.M), sorted(set(re.findall(r"(?:SB_|syncBridge)\w*", text))),
            'setAttr ".etw" yes' in text, text)


def shape_of(tr):
    return cmds.listRelatives(tr, shapes=True, fullPath=True)[0]


cmds.file(new=True, force=True)
cam = cmds.camera(name="SHOT_CAM")[0]
cmds.select(cam)
layer_mapping.add_layer("BG")
ded = cleanup.dedicated_cameras()[0]
cmds.setKeyframe(shape_of(ded), attribute="filmTranslateH", time=1, value=0.0)
cmds.setKeyframe(shape_of(ded), attribute="filmTranslateH", time=10, value=0.2)
timing.set_origin(1001)
key_markers._ensure_bookmark_plugin()
key_markers._write({"markers": [{"index": 1, "label": "k1", "frame": 1001}, {"index": 2, "label": "k2", "frame": 1010}]})
cmds.createNode("timeSliderBookmark", name="myBookmark", skipSelect=True)
key_markers.restore_overlay()
comp_guide.show({"name": "main", "width": 1920, "height": 1080, "pixelAspect": 1.0}, camera=cam)
viewer_camera.ensure(shape_of(ded))
cmds.setAttr("time1.enableTimewarp", 1)
cmds.setKeyframe("time1", attribute="outTime", time=1, value=1)
cmds.setKeyframe("time1", attribute="outTime", time=24, value=30)

found = cleanup.inventory()
check("inventory", found["any"] and len(found["cameras"]) == 1 and found["cameras"][0]["keys"] == 2
      and found["layer_map"] and found["bookmarks"] == 2 and found["origin"] == 1001 and found["display"] > 0,
      str({k: v for k, v in found.items() if k != "cameras"}))

# keep the cameras
result = cleanup.run(keep_cameras=True)
check("backup written", result["backup"] and os.path.isfile(result["backup"]), str(result["backup"]))
check("camera kept, plain", cmds.objExists(ded) and not cmds.attributeQuery(layer_camera.MARK_ATTR, node=ded, exists=True)
      and not cmds.getAttr(ded + ".translateX", lock=True))
check("camera keys and link kept",
      cmds.keyframe(shape_of(ded) + ".filmTranslateH", q=True, keyframeCount=True) == 2
      and cmds.isConnected(shape_of(cam) + ".focalLength", shape_of(ded) + ".focalLength"))
check("nothing else of ours", not cleanup.inventory()["any"] and not result["leftovers"], str(result["leftovers"]))
reqs, names, warp, text = saved("keep.ma")
check("keep: saved names", set(names) == {"SB_BG_CAM", "SB_BG_CAMShape", "SB_BG_CAMShape_filmTranslateH"}, str(names))
check("keep: time warp and the user's bookmark", warp and "myBookmark" in text)
cmds.undo()
check("keep: one undo", cmds.attributeQuery(layer_camera.MARK_ATTR, node=ded, exists=True)
      and cmds.objExists(layer_mapping.DATA_NODE) and cmds.objExists(key_markers.DATA_NODE)
      and cmds.objExists(timing.NODE) and len(key_markers.our_bookmarks()) == 2)

# delete the cameras
viewer_camera.ensure(shape_of(ded))
cmds.delete("myBookmark")
result = cleanup.run(keep_cameras=False, backup=False)
check("camera deleted, original kept", not cmds.objExists(ded) and cmds.objExists(cam))
reqs, names, warp, text = saved("delete.ma")
check("delete: nothing of ours saved", not names, str(names))
check("delete: only Maya's requires", all(r.startswith("requires maya ") for r in reqs), str(reqs))
check("delete: time warp kept", warp)
cmds.undo()
check("delete: one undo", cmds.objExists(ded)
      and cmds.keyframe(shape_of(ded) + ".filmTranslateH", q=True, keyframeCount=True) == 2)

print("RESULT %s" % ("PASS" if all(checks) else "FAIL"))
maya.standalone.uninitialize()
