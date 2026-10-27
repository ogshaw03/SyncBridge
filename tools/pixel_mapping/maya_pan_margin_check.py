"""mayapy: a null parent's PAN (H-AE-30) and a render with a margin around the comp (D-36).

    mayapy tools/pixel_mapping/maya_pan_margin_check.py

The render is 2112x1188 around a 1920x1080 comp. A BG layer is linked (relative, 2D Pan/Zoom) and its
reference recorded; then AE moves it by 80 px right / 30 px up, once by its own position and once by
a null parent. Each time the dedicated camera must move the picture by exactly that many render
pixels (the camera model of core.pixel_mapping, which the renders confirmed).
"""
import os
import sys

import maya.standalone
maya.standalone.initialize()
import maya.cmds as cmds  # noqa: E402

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path[:0] = [os.path.join(REPO, "src"), os.path.join(REPO, "maya_plugin", "scripts")]
from syncbridge.core import pixel_mapping as pm  # noqa: E402
from syncbridge_maya import layer_mapping, pixel_mapping  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print("%s  %s %s" % ("OK" if ok else "NG", name, detail))


cmds.file(new=True, force=True)
for attr, value in (("width", 2112), ("height", 1188), ("deviceAspectRatio", 2112 / 1188.0), ("pixelAspect", 1.0)):
    cmds.setAttr("defaultResolution." + attr, value)
cam, shape = cmds.camera(name="SHOT_CAM")
cmds.setAttr(cam + ".translateZ", 30)
cmds.select(cam, cmds.polyCube()[0])
layer, _ = layer_mapping.add_layer("BG")
layer_mapping.set_defaults(method="pan_zoom")
layer_mapping.connect({"comp_id": 1, "comp": "c", "layer_id": 5, "layer": "BG", "source": "bg",
                       "source_width": 6000, "source_height": 4000}, layer["id"], "pan_zoom", "relative")
COMP = {"id": 1, "name": "c", "width": 1920, "height": 1080, "pixelAspect": 1, "time": 0}
NULL = {"name": "PAN", "position": [960.0, 540.0], "anchorPoint": [50.0, 50.0], "scale": [100.0, 100.0],
        "rotation": 0.0, "threeD": False}


def send(position, parents=None):
    layer_info = {"id": 5, "name": "BG", "position": list(position), "anchorPoint": [3000.0, 2000.0],
                  "scale": [100.0, 100.0], "rotation": 0.0, "threeD": False, "effects": [], "source": "bg",
                  "source_width": 6000, "source_height": 4000,
                  "parent": parents[0]["name"] if parents else None, "parents": parents or []}
    return pixel_mapping.apply_from_ae({"comp": COMP, "layer": layer_info})


def picture_x(point=(1.0, 2.0, -20.0)):
    """Where a camera-space point lands in the render through the dedicated camera now."""
    cam_data = dict(pixel_mapping.camera_data(layer["layer_camera"]))
    return pm.project(cam_data, pixel_mapping.render_data(), point)


r0 = send((960.0, 540.0))
check("reference recorded", r0.get("reference_recorded"))
before = picture_x()
send((1040.0, 510.0))
moved = picture_x()
check("own position: the picture moves 80 px right, 30 px up in the render",
      abs(moved[0] - before[0] - 80.0) < 1e-6 and abs(moved[1] - before[1] + 30.0) < 1e-6,
      (round(moved[0] - before[0], 6), round(moved[1] - before[1], 6)))
send((960.0, 540.0))                                          # back at the reference
back = picture_x()
check("back at the reference", abs(back[0] - before[0]) < 1e-6)
# the same move by a null parent: the BG keeps its position in the null's space
child = (50.0, 50.0)                                          # at the null's anchor: the null's position is the BG's
send(child, [dict(NULL)])
same = picture_x()
check("parent at rest = no move", abs(same[0] - before[0]) < 1e-6, round(same[0] - before[0], 6))
send(child, [dict(NULL, position=[1040.0, 510.0])])
panned = picture_x()
check("null parent PAN: the same 80 / -30 px", abs(panned[0] - moved[0]) < 1e-6 and abs(panned[1] - moved[1]) < 1e-6,
      (round(panned[0] - before[0], 6), round(panned[1] - before[1], 6)))

# -- the reference holds the base values, not keys of an earlier transfer (the user, 2026-10-25) --------
from syncbridge_maya import motion  # noqa: E402
own = layer["layer_camera"]
cmds.setAttr(own + ".panZoomEnabled", True)
cmds.setKeyframe(own, attribute="horizontalPan", time=1, value=0.37)      # as if animated before
link = layer_mapping.stored()[0]
layer_mapping.reset_reference(link["id"])
send((960.0, 540.0))
ref = layer_mapping.stored()[0]["reference"]
check("reference camera values are the base (0), not the keyed 0.37", ref["camera"]["hpan"] == 0.0, ref["camera"])
cmds.cutKey(own, attribute="horizontalPan", clear=True)

# -- a BG inside a precomp, the precomp layer pans in the main comp (D-37) -------------------------------
cmds.select(cam, cmds.polySphere()[0])
inner_layer, _ = layer_mapping.add_layer("BG_IN")
VIA = [{"comp_id": 1, "comp": "c", "layer_id": 70, "layer": "SC_PRE"}]
inner_ae = {"comp_id": 40, "comp": "SC_PRE", "layer_id": 9, "layer": "BG_IN", "source": "bg", "source_width": 6000,
            "source_height": 4000, "via": VIA}
layer_mapping.connect(inner_ae, inner_layer["id"], "pan_zoom", "relative")
inner_link = [m for m in layer_mapping.stored() if m["ae"].get("via")][0]
try:
    pixel_mapping.apply_from_ae({"comp": dict(COMP, id=40, name="SC_PRE"), "layer": {
        "id": 9, "name": "BG_IN", "position": [960.0, 540.0], "anchorPoint": [3000.0, 2000.0], "scale": [100, 100],
        "rotation": 0.0, "threeD": False, "effects": [], "source": "bg", "source_width": 6000, "source_height": 4000,
        "parent": None, "parents": []}})
    check("the AE panel cannot send a layer inside a precomp", False)
except ValueError as exc:
    check("the AE panel cannot send a layer inside a precomp", u"プリコンポ" in str(exc), str(exc)[:40])
PRE = {"name": "SC_PRE", "anchorPoint": [960.0, 540.0], "scale": [100.0, 100.0], "rotation": 0.0, "threeD": False,
       "parents": []}


def nested_reply(times, pre_x):
    samples = [{"t": t, "position": [960.0, 540.0], "anchorPoint": [3000.0, 2000.0], "scale": [100.0, 100.0],
                "rotation": 0.0, "parents": [], "containers": [dict(PRE, position=[pre_x(t), 540.0])]}
               for t in times]
    return {"comp": COMP, "layer": {"name": "BG_IN", "threeD": False, "parent": None, "effects": [],
                                    "source_width": 6000, "source_height": 4000}, "samples": samples}


q = motion.query(inner_link["id"], 1, 1, origin=1)
motion.record_reference(inner_link["id"], 1, nested_reply(q["request"]["times"], lambda t: 960.0))
check("reference recorded from Maya (frame 1)", layer_mapping.stored()[[m["id"] for m in layer_mapping.stored()]
                                                  .index(inner_link["id"])]["reference"] is not None)
inner_own = layer_mapping.store()["maya_layers"][-1]["layer_camera"]
cmds.currentTime(1)
start = pm.project(dict(pixel_mapping.camera_data(inner_own)), pixel_mapping.render_data(), (1.0, 2.0, -20.0))
q = motion.query(inner_link["id"], 1, 3, origin=1)
p = motion.plan(inner_link["id"], q["frames"], nested_reply(q["request"]["times"], lambda t: 960.0 + 40.0 * t * 24))
motion.apply(p, confirm=False)
cmds.currentTime(3)
end = pm.project(dict(pixel_mapping.camera_data(inner_own)), pixel_mapping.render_data(), (1.0, 2.0, -20.0))
check("the precomp layer's pan (80 px at frame 3) moves the inner BG's camera 80 px", abs(end[0] - start[0] - 80.0) < 1e-6,
      round(end[0] - start[0], 6))
for f in os.listdir(os.path.join(os.path.expanduser("~"), "Documents", "maya", "SyncBridge", "backups")):
    if f.startswith("motion_"):
        os.remove(os.path.join(os.path.expanduser("~"), "Documents", "maya", "SyncBridge", "backups", f))
for f in os.listdir(os.path.join(os.path.expanduser("~"), "Documents", "maya", "SyncBridge", "backups")):
    if f.startswith("pixelmap_"):
        os.remove(os.path.join(os.path.expanduser("~"), "Documents", "maya", "SyncBridge", "backups", f))
print("RESULT", "PASS" if all(checks) else "FAIL")
maya.standalone.uninitialize()
os._exit(0)
