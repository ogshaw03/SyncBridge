"""mayapy: Phase 3 (D-30), the AE layer's motion as keys on the dedicated camera.

    mayapy tools/pixel_mapping/maya_motion_check.py

1. H-MY-31: camera_data(camera, time=f) (getAttr -time) equals reading the camera at frame f.
2. A 48-frame AE motion (a pan and a push-in) keyed on the BG layer's dedicated camera: every frame's
   keyed values equal a single send's solution at that frame, the readback passes, the original camera
   and its camera work are untouched.
3. Keys outside the range stay, a second transfer replaces the keys in the range, undo removes them.
Prints "OK" / "NG" per check and "RESULT PASS" / "RESULT FAIL".
"""
import os
import sys

import maya.standalone
maya.standalone.initialize()
import maya.cmds as cmds  # noqa: E402

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path[:0] = [os.path.join(REPO, "src"), os.path.join(REPO, "maya_plugin", "scripts")]
from syncbridge.core import pixel_mapping as pm  # noqa: E402
from syncbridge_maya import layer_mapping, motion, pixel_mapping  # noqa: E402

W, H = 1920, 1080
checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print("%s  %s %s" % ("OK" if ok else "NG", name, detail))


cmds.file(new=True, force=True)
cmds.currentUnit(time="film")
for attr, value in (("width", W), ("height", H), ("deviceAspectRatio", float(W) / H), ("pixelAspect", 1.0)):
    cmds.setAttr("defaultResolution." + attr, value)
cam, shape = cmds.camera(name="SHOT_CAM")
shape = cmds.ls(shape, long=True)[0]
cmds.setAttr(shape + ".horizontalFilmAperture", 1.417)
cmds.setAttr(shape + ".verticalFilmAperture", 0.797)
for t, tx, focal in ((1001, -1.0, 35.0), (1048, 1.0, 42.0)):           # camera work
    cmds.setKeyframe(cam, attribute="translateX", time=t, value=tx)
    cmds.setKeyframe(shape, attribute="focalLength", time=t, value=focal)
cmds.setAttr(cam + ".translateZ", 30)
cmds.currentTime(1001)

# -- 1. H-MY-31 ----------------------------------------------------------------------------------------
worst = 0.0
for f in (1001, 1013.5, 1030, 1048):
    by_time = pixel_mapping.camera_data(shape, time=f)
    cmds.currentTime(f)
    now = pixel_mapping.camera_data(shape)
    worst = max([worst] + [abs(a - b) for a, b in zip(by_time["world_inverse"], now["world_inverse"])] +
                [abs(by_time["focal_length"] - now["focal_length"])])
check("H-MY-31 getAttr -time equals the camera at that frame", worst < 1e-9, "max diff %.2e" % worst)
cmds.currentTime(1001)

# -- 2. the motion -------------------------------------------------------------------------------------
cmds.select(cam)
layer, _ = layer_mapping.add_layer("BG")
own = layer["layer_camera"]
COMP = {"id": 1, "name": "c010", "width": W, "height": H, "pixelAspect": 1, "frameRate": 24, "time": 0}
LAYER = {"id": 5, "name": "BG", "threeD": False, "parent": None, "effects": [], "source": "bg",
         "source_width": 6000, "source_height": 4000}


def transform(i):
    """AE: the BG pans right / up and pushes in from 100 % to 112 % over 48 frames."""
    return {"position": [960.0 + 6.25 * i, 540.0 - 2.5 * i], "anchorPoint": [3000.0, 2000.0],
            "scale": [100.0 + 0.25 * i] * 2, "rotation": 0.0}


layer_mapping.set_defaults(method="pan_zoom")
layer_mapping.connect({"comp_id": 1, "comp": "c010", "layer_id": 5, "layer": "BG", "source": "bg",
                       "source_width": 6000, "source_height": 4000}, layer["id"])
first = pixel_mapping.apply_from_ae({"comp": COMP, "layer": dict(LAYER, **transform(0))})
check("reference recorded at frame 1001", first.get("reference_recorded"))
link = layer_mapping.stored()[0]


def transfer(start, end, shift=0.0):
    q = motion.query(link["id"], start, end, origin=1001)
    samples = []
    for t in q["request"]["times"]:
        s = transform(t * 24.0)
        s["position"][0] += shift
        samples.append(dict(s, t=t))
    p = motion.plan(link["id"], q["frames"], {"comp": COMP, "layer": LAYER, "samples": samples})
    return p, motion.apply(p, confirm=False)


cmds.setKeyframe(own, attribute="horizontalPan", time=1100, value=0.5)   # a key outside the range
p, result = transfer(1001, 1048)
check("applied 48 frames", result["status"] == "applied" and result["count"] == 48, result["attrs"])
check("readback", result["readback"]["passed"], result["readback"])
check("solver error", result["max_error_px"] < 0.01, "%.4f px" % result["max_error_px"])
ref = link["reference"]
worst = 0.0
for f in (1001, 1012, 1027, 1048):
    m, _ = pm.ae_layer_matrix(dict(LAYER, **transform(f - 1001)))
    single = pm.solve_relative("pan_zoom", dict(pixel_mapping.camera_data(own, time=f), **ref["camera"]),
                               pixel_mapping.render_data(), COMP, ref["matrix"], m)
    for key in ("hpan", "vpan", "zoom"):
        worst = max(worst, abs(cmds.getAttr("%s.%s" % (own, pixel_mapping.CAMERA_ATTRS[key]), time=f)
                               - single["values"][key]))
check("keyed values equal single sends at 1001 / 1012 / 1027 / 1048", worst < 1e-9, "max diff %.2e" % worst)
check("zoom follows the push-in (1 / 1.1175 at 1048)",
      abs(cmds.getAttr(own + ".zoom", time=1048) - 1.0 / 1.1175) < 1e-9)
check("original camera has no 2D keys", not cmds.keyframe(shape + ".horizontalPan", query=True)
      and cmds.getAttr(shape + ".horizontalPan") == 0.0)
check("key outside the range stays", cmds.keyframe(own + ".horizontalPan", query=True, time=(1100, 1100)) == [1100.0])

# -- 3. again, and undo --------------------------------------------------------------------------------
before_again = cmds.getAttr(own + ".horizontalPan", time=1024)
p2, result2 = transfer(1001, 1048, shift=40.0)
check("second transfer replaces the 48 keys", result2["replaced"].get("horizontalPan") == 48
      and len(cmds.keyframe(own + ".horizontalPan", query=True, time=(1001, 1048))) == 48)
check("values changed", cmds.getAttr(own + ".horizontalPan", time=1024) != before_again)
cmds.undo()
check("undo brings the first transfer back", abs(cmds.getAttr(own + ".horizontalPan", time=1024) - before_again) < 1e-12)
cmds.undo()
check("undo again removes the keys in the range",
      not cmds.keyframe(own + ".horizontalPan", query=True, time=(1001, 1048)))

# -- 4. every link at once ("すべてのアニメーションを転送") -------------------------------------------
cmds.select(cam)
char, _ = layer_mapping.add_layer("CHAR")
char_ae = {"comp_id": 1, "comp": "c010", "layer_id": 6, "layer": "CHAR", "source": "char",
           "source_width": 6000, "source_height": 4000}
layer_mapping.connect(char_ae, char["id"])
links, skipped = motion.transferable(layer_mapping.store())
check("a link without a reference is left out", [m["ae"]["layer"] for m in links] == ["BG"]
      and len(skipped) == 1 and "CHAR" in skipped[0], skipped)
pixel_mapping.apply_from_ae({"comp": COMP, "layer": dict(LAYER, id=6, name="CHAR", **transform(0))})
links, skipped = motion.transferable(layer_mapping.store())
plans = []
for m in links:
    q = motion.query(m["id"], 1001, 1024, origin=1001)
    sign = 1.0 if m["ae"]["layer"] == "BG" else -1.0       # CHAR moves the other way
    samples = []
    for t in q["request"]["times"]:
        s = transform(t * 24.0)
        s["position"][0] = 960.0 + sign * (s["position"][0] - 960.0)
        samples.append(dict(s, t=t))
    plans.append(motion.plan(m["id"], q["frames"], {"comp": COMP, "layer": dict(LAYER, name=m["ae"]["layer"]),
                                                     "samples": samples}))
results = motion.apply_all(plans, confirm=False)
char_own = [layer for layer in layer_mapping.store()["maya_layers"] if layer["name"] == "CHAR"][0]["layer_camera"]
bg_pan, char_pan = (cmds.getAttr(c + ".horizontalPan", time=1024) for c in (own, char_own))
check("both cameras keyed, in opposite directions", len(results) == 2 and all(r["readback"]["passed"] for r in results)
      and bg_pan * char_pan < 0, (bg_pan, char_pan))
cmds.undo()
check("one undo removes the keys of both", not cmds.keyframe(char_own + ".horizontalPan", query=True)
      and not cmds.keyframe(own + ".horizontalPan", query=True, time=(1001, 1024)))
for path in [result["backup"], result2["backup"]] + [r["backup"] for r in results]:
    if os.path.isfile(path):
        os.remove(path)

print("RESULT", "PASS" if all(checks) else "FAIL")
maya.standalone.uninitialize()
os._exit(0)
