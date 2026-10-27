"""mayapy: source camera mode (D-39) by renders.

    mayapy tools/pixel_mapping/maya_source_camera_check.py [out folder]

A wide BG plate is rendered by a plate camera (film back x3) at 1920x1080. In AE that plate sits at
100 % in a 640x360 comp, moved by whole pixels, so the comp shows an exact crop of the plate. In Maya the
plate camera is the BG layer's camera; one send in source camera mode (no reference) sets its dedicated
camera, which is then rendered at 640x360 and compared with the crop pixel by pixel. Colored boxes at
several depths (parallax would show a wrong camera position at once). Hardware 2.0, no textures.
"""
import os
import sys

import maya.standalone
maya.standalone.initialize()
import maya.cmds as cmds  # noqa: E402

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path[:0] = [os.path.join(REPO, "src"), os.path.join(REPO, "maya_plugin", "scripts")]
from syncbridge.pixelcheck import png  # noqa: E402
from syncbridge_maya import layer_mapping, pixel_mapping  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ.get("TEMP", "."), "syncbridge_source_check")
os.makedirs(OUT, exist_ok=True)
W, H = 640, 360                       # the comp = the scene's render size
PW, PH = 1920, 1080                   # the plate: 3x the film back, 3x the pixels (same density)
checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print("%s  %s %s" % ("OK" if ok else "NG", name, detail))


def set_resolution(w, h):
    for attr, value in (("width", w), ("height", h), ("deviceAspectRatio", float(w) / h), ("pixelAspect", 1.0)):
        cmds.setAttr("defaultResolution." + attr, value)


def render(camera, w, h, name):
    set_resolution(w, h)
    cmds.setAttr("defaultRenderGlobals.imageFilePrefix", name, type="string")
    return png.read(cmds.ogsRender(camera=camera, width=w, height=h))


cmds.file(new=True, force=True)
cmds.workspace(fileRule=["images", OUT])
cmds.setAttr("defaultRenderGlobals.imageFormat", 32)
cmds.setAttr("defaultRenderGlobals.currentRenderer", "mayaHardware2", type="string")
colors = [(0.9, 0.2, 0.2), (0.2, 0.8, 0.3), (0.2, 0.4, 0.9), (0.9, 0.8, 0.2), (0.7, 0.3, 0.8), (0.2, 0.8, 0.8)]
for i in range(18):
    box = cmds.polyCube(name="box%d" % i, width=2, height=2 + (i % 4), depth=2)[0]
    cmds.setAttr(box + ".translate", -16 + (i % 6) * 6.5, (i % 3) * 2.0 - 2.0, -10.0 - (i // 6) * 12.0)
    cmds.setAttr(box + ".rotateY", i * 17)
    shader = cmds.shadingNode("surfaceShader", asShader=True)
    cmds.setAttr(shader + ".outColor", *colors[i % len(colors)], type="double3")
    sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
    cmds.connectAttr(shader + ".outColor", sg + ".surfaceShader")
    cmds.sets(box, edit=True, forceElement=sg)
plate_cam, plate_shape = cmds.camera(name="PLATE_CAM")
plate_shape = cmds.ls(plate_shape, long=True)[0]
cmds.setAttr(plate_cam + ".translate", 1.0, 1.5, 12.0)
cmds.setAttr(plate_shape + ".horizontalFilmAperture", 1.417 * 3)
cmds.setAttr(plate_shape + ".verticalFilmAperture", 1.417 * 3 * PH / PW)
cmds.setAttr(plate_shape + ".filmFit", 1)
cmds.setAttr(plate_shape + ".focalLength", 35.0)

plate = render(plate_shape, PW, PH, "plate")                  # the BG material that AE gets
set_resolution(W, H)
cmds.select(plate_cam, cmds.ls("box*", type="transform"))
layer, _ = layer_mapping.add_layer("BG")
layer_mapping.set_defaults(method="pan_zoom", mode="source")
layer_mapping.connect({"comp_id": 1, "comp": "c", "layer_id": 5, "layer": "BG", "source": "plate",
                       "source_width": PW, "source_height": PH}, layer["id"], "pan_zoom", "source")
own = layer["layer_camera"]
check("linked in source camera mode", layer_mapping.stored()[0]["mode"] == "source")
COMP = {"id": 1, "name": "c", "width": W, "height": H, "pixelAspect": 1, "time": 0}

for name, (dx, dy) in (("centered", (0, 0)), ("slid", (437, -213)), ("slid more", (-602, 351))):
    # AE: the plate's anchor at its center, the layer moved so the comp shows plate pixels (x + ox, y + oy)
    position = [W / 2.0 + dx, H / 2.0 + dy]
    info = {"comp": COMP, "layer": {"id": 5, "name": "BG", "position": position, "anchorPoint": [PW / 2.0, PH / 2.0],
                                    "scale": [100.0, 100.0], "rotation": 0.0, "threeD": False, "effects": [],
                                    "source": "plate", "source_width": PW, "source_height": PH, "parent": None,
                                    "parents": []}}
    result = pixel_mapping.apply_from_ae(info)
    got = render(own, W, H, "dedicated_" + name.replace(" ", "_"))
    ox, oy = int(PW / 2 - W / 2 - dx), int(PH / 2 - H / 2 - dy)    # comp pixel (x, y) shows plate pixel (x+ox, y+oy)
    total, worst, n = 0, 0, 0
    for y in range(4, H - 4):
        for x in range(4, W - 4):
            a = got.get(x, y)
            b = plate.get(x + ox, y + oy)
            d = max(abs(a[c] - b[c]) for c in range(3))
            total += d
            worst = max(worst, d)
            n += 1
    mean = total / float(n)
    check("%s: the dedicated camera's render = the plate's crop (zoom %.4f)" % (name, result["values"]["zoom"]),
          mean < 0.5 and result["status"] == "applied", "mean diff %.3f / 255, max %d" % (mean, worst))

for f in os.listdir(os.path.join(os.path.expanduser("~"), "Documents", "maya", "SyncBridge", "backups")):
    if f.startswith("pixelmap_"):
        os.remove(os.path.join(os.path.expanduser("~"), "Documents", "maya", "SyncBridge", "backups", f))
print("RESULT", "PASS" if all(checks) else "FAIL")
maya.standalone.uninitialize()
os._exit(0)
