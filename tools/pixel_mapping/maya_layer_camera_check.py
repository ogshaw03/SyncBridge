"""mayapy: the dedicated cameras of the Maya layers (D-29, H-MY-30).

    mayapy tools/pixel_mapping/maya_layer_camera_check.py <out folder>

1. A camera with camera work (translate / rotate / focal length keys) gets a dedicated camera for a
   Maya layer: the same world matrix and lens at every checked frame, and the same Hardware 2.0 render.
2. BG and CHAR use the same camera: each Maya layer has its own dedicated camera, and a send from AE
   moves only the camera of the layer it is linked to (both play at the same time).
3. Rename, another camera, removal and undo.
Prints "OK" / "NG" per check and "RESULT PASS" / "RESULT FAIL".
"""
import os
import sys

import maya.standalone
maya.standalone.initialize()
import maya.cmds as cmds  # noqa: E402

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path[:0] = [os.path.join(REPO, "src"), os.path.join(REPO, "maya_plugin", "scripts")]
from syncbridge.core import layer_mapping as core_lm  # noqa: E402
from syncbridge.pixelcheck import png  # noqa: E402
from syncbridge_maya import layer_camera, layer_mapping, pixel_mapping  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
os.makedirs(OUT, exist_ok=True)
W, H = 640, 360
checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print("%s  %s %s" % ("OK" if ok else "NG", name, detail))


cmds.file(new=True, force=True)
cmds.workspace(fileRule=["images", OUT])
for attr, value in (("width", W), ("height", H), ("deviceAspectRatio", float(W) / H), ("pixelAspect", 1.0)):
    cmds.setAttr("defaultResolution." + attr, value)
cmds.setAttr("defaultRenderGlobals.imageFormat", 32)
cmds.setAttr("defaultRenderGlobals.currentRenderer", "mayaHardware2", type="string")
for i, (x, z) in enumerate(((-3, 0), (0, -8), (4, -20), (1, 3))):
    cube = cmds.polyCube(name="box%d" % i, w=1 + i, h=1 + i * 0.5, d=1)[0]
    cmds.setAttr(cube + ".translate", x, 0, z)
    cmds.setAttr(cube + ".rotate", 10 * i, 25 * i, 0)

cam, shape = cmds.camera(name="SHOT_CAM")
shape = cmds.ls(shape, long=True)[0]
cmds.setAttr(shape + ".farClipPlane", 1000)
for t, tx, ry, focal in ((1, -2.0, -10.0, 30.0), (24, 2.5, 12.0, 55.0)):
    cmds.setKeyframe(cam, attribute="translateX", time=t, value=tx)
    cmds.setKeyframe(cam, attribute="rotateY", time=t, value=ry)
    cmds.setKeyframe(shape, attribute="focalLength", time=t, value=focal)
cmds.setAttr(cam + ".translateZ", 12)
cmds.setAttr(cam + ".translateY", 1.5)
cmds.setAttr(shape + ".horizontalFilmOffset", 0.03)          # a fixed 2D value: copied to the dedicated camera


def layer_by_name(name):
    return [layer for layer in layer_mapping.store()["maya_layers"] if layer["name"] == name][0]


# -- 1. same view --------------------------------------------------------------------------------------
cmds.select(cam, "box0", "box1")
bg, warnings = layer_mapping.add_layer("BG")
own = bg["layer_camera"]
check("dedicated camera under the original", cmds.listRelatives(own, parent=True, fullPath=True)[0].startswith(
    cmds.ls(cam, long=True)[0] + "|SB_BG_CAM"), own)
check("objects recorded", sorted(core_lm.short_name(o["name"]) for o in bg["objects"]) == ["box0", "box1"])
check("no warning (the original's 2D values are not keyed)", warnings == [], warnings)
check("transform locked", cmds.getAttr(cmds.listRelatives(own, parent=True, fullPath=True)[0] + ".tx", lock=True))
worst = 0.0
for frame in (1, 7.5, 13, 24):
    cmds.currentTime(frame)
    a = cmds.getAttr(shape + ".worldMatrix[0]")
    b = cmds.getAttr(own + ".worldMatrix[0]")
    worst = max([worst] + [abs(x - y) for x, y in zip(a, b)])
    for attr in ("focalLength", "horizontalFilmOffset", "horizontalFilmAperture", "nearClipPlane"):
        if abs(cmds.getAttr(shape + "." + attr) - cmds.getAttr(own + "." + attr)) > 1e-9:
            worst = max(worst, 1.0)
check("same world matrix and lens at frames 1 / 7.5 / 13 / 24", worst < 1e-9, "max diff %.2e" % worst)

cmds.currentTime(13)
renders = []
for name, camera in (("original", shape), ("dedicated", own)):
    cmds.setAttr("defaultRenderGlobals.imageFilePrefix", "layercam_" + name, type="string")
    renders.append(png.read(cmds.ogsRender(camera=camera, width=W, height=H)))
diff = max(abs(p - q) for ra, rb in zip(renders[0].rows, renders[1].rows) for p, q in zip(ra, rb))
check("same Hardware 2.0 render (frame 13)", diff == 0, "max channel diff %d" % diff)

# -- 2. BG and CHAR on the same camera -----------------------------------------------------------------
cmds.select(cam, "box2")
char, _ = layer_mapping.add_layer("CHAR")
check("CHAR has its own dedicated camera", char["layer_camera_uuid"] != bg["layer_camera_uuid"]
      and "SB_CHAR_CAM" in char["layer_camera"])
COMP = {"id": 1, "name": "c010", "width": W, "height": H, "pixelAspect": 1, "time": 0}


def info(layer_id, name, position):
    return {"comp": COMP, "layer": {"id": layer_id, "name": name, "position": list(position),
                                    "anchorPoint": [W / 2.0, H / 2.0], "scale": [100, 100], "rotation": 0,
                                    "threeD": False, "parent": None, "effects": [], "source": name,
                                    "source_width": W, "source_height": H}}


layer_mapping.connect(pixel_mapping._ae_layer(info(10, "BG", (320, 180))), bg["id"])
layer_mapping.connect(pixel_mapping._ae_layer(info(11, "CHAR", (320, 180))), char["id"])
for layer_id, name in ((10, "BG"), (11, "CHAR")):
    r = pixel_mapping.apply_from_ae(info(layer_id, name, (320, 180)))
    check("reference recorded: %s" % name, r["status"] == "unchanged" and r.get("reference_recorded"))
char_own = layer_by_name("CHAR")["layer_camera"]
before = {n: (cmds.getAttr(c + ".horizontalPan"), cmds.getAttr(c + ".verticalPan"))
          for n, c in (("BG", own), ("CHAR", char_own), ("SHOT", shape))}
r = pixel_mapping.apply_from_ae(info(10, "BG", (380, 150)))         # only BG moves in AE
after = {n: (cmds.getAttr(c + ".horizontalPan"), cmds.getAttr(c + ".verticalPan"))
         for n, c in (("BG", own), ("CHAR", char_own), ("SHOT", shape))}
check("BG send moves the BG camera", r["status"] == "applied" and after["BG"] != before["BG"], after["BG"])
check("CHAR camera and the original are unchanged", after["CHAR"] == before["CHAR"] and after["SHOT"] == before["SHOT"])
r = pixel_mapping.apply_from_ae(info(11, "CHAR", (300, 200)))
after2 = {n: (cmds.getAttr(c + ".horizontalPan"), cmds.getAttr(c + ".verticalPan"))
          for n, c in (("BG", own), ("CHAR", char_own))}
check("CHAR send moves only the CHAR camera", after2["CHAR"] != before["CHAR"] and after2["BG"] == after["BG"])
cmds.currentTime(20)
check("camera work still reaches both dedicated cameras",
      max(abs(x - y) for x, y in zip(cmds.getAttr(shape + ".worldMatrix[0]"),
                                     cmds.getAttr(char_own + ".worldMatrix[0]"))) < 1e-9)

# -- 3. rename, another camera, removal, undo ----------------------------------------------------------
layer_mapping.rename_layer(bg["id"], "BG_town")
renamed = layer_by_name("BG_town")
check("rename renames the dedicated camera", "SB_BG_town_CAM" in renamed["layer_camera"]
      and all(m["maya"]["camera"] == renamed["layer_camera"] for m in core_lm.links_of(layer_mapping.store(), bg["id"])))
cam2 = cmds.camera(name="ALT_CAM")[0]
cmds.select(cam2)
moved, _ = layer_mapping.set_camera_from_selection(char["id"])
check("another camera: the dedicated camera moves under it", moved["layer_camera"].startswith(
    cmds.ls(cam2, long=True)[0] + "|") and moved["layer_camera_uuid"] == char["layer_camera_uuid"])
cmds.select(moved["layer_camera"])
try:
    layer_mapping.set_camera_from_selection(bg["id"])
    check("a dedicated camera cannot be the original", False)
except ValueError:
    check("a dedicated camera cannot be the original", True)
cmds.setKeyframe(shape, attribute="horizontalFilmOffset", time=1, value=0.0)
cmds.select(cam)
_, warnings = layer_mapping.set_camera_from_selection(char["id"])
check("warning: the original's keyed 2D values do not reach the dedicated camera",
      len(warnings) == 1 and "horizontalFilmOffset" in warnings[0], warnings)
own_char = layer_by_name("CHAR")["layer_camera"]
layer_mapping.remove_layer(char["id"])
check("removal deletes the dedicated camera", not cmds.objExists(own_char))
cmds.undo()
check("undo brings the layer and its camera back", cmds.objExists(own_char)
      and any(layer["id"] == char["id"] for layer in layer_mapping.store()["maya_layers"]))

print("RESULT", "PASS" if all(checks) else "FAIL")
maya.standalone.uninitialize()
os._exit(0)
