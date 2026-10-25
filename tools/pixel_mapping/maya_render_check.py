r"""Pixel Mapping Phase 1 check in Maya (docs/PIXEL_MAPPING.md): AE BG positions -> core solver ->
Maya camera (Film Offset / Film Translate / 2D Pan-Zoom) -> render -> markers vs where AE shows them.

    "C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe" tools\pixel_mapping\maya_render_check.py <out_dir> <sw|hw> [variant]

sw = Maya Software (file texture filter: Mipmap), hw = Hardware 2.0 (ogsRender, texture size limit off).
variant: persp (focal 35, film 1.417 x 0.797, horizontal fit), persp32 (3:2 film, fill fit, camera and
BG moved and rotated together), ortho (film translate only). The test BG is written to <out_dir>
when missing. Prints one RESULT line per method and position; results go to <out_dir>/e2e_*.json.
"""
import json
import os
import sys

import maya.standalone
maya.standalone.initialize()
import maya.cmds as cmds

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path[:0] = [os.path.join(REPO, "src"), os.path.join(REPO, "maya_plugin", "scripts")]
from syncbridge.core import pixel_mapping as pm
from syncbridge.pixelcheck import measure, png, testgrid
from syncbridge_maya import pixel_mapping as maya_pm

OUT, RENDERER = sys.argv[1], sys.argv[2]
VARIANT = sys.argv[3] if len(sys.argv) > 3 else "persp"
os.makedirs(OUT, exist_ok=True)
GRID = os.path.join(OUT, "testgrid_6000x4000.png").replace("\\", "/")
if not os.path.exists(GRID):
    png.write(GRID, testgrid.make(6000, 4000))
W, H = 1920, 1080
cmds.workspace(fileRule=["images", OUT])
for attr, value in (("width", W), ("height", H), ("deviceAspectRatio", float(W) / H), ("pixelAspect", 1.0)):
    cmds.setAttr("defaultResolution." + attr, value)
cmds.setAttr("defaultRenderGlobals.imageFormat", 32)
cmds.setAttr("defaultRenderGlobals.enableDefaultLight", 0)
cmds.setAttr("hardwareRenderingGlobals.enableTextureMaxRes", False)

# BG plane, placed in the world the way a layout artist might: scaled, moved, but facing the camera.
plane = cmds.polyPlane(name="bgPlane", w=60, h=40, sx=4, sy=3, ax=(0, 0, 1))[0]
shader = cmds.shadingNode("surfaceShader", asShader=True)
tex = cmds.shadingNode("file", asTexture=True)
cmds.setAttr(tex + ".fileTextureName", GRID, type="string")
cmds.setAttr(tex + ".filterType", 1)
cmds.connectAttr(tex + ".outColor", shader + ".outColor")
sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
cmds.connectAttr(shader + ".outColor", sg + ".surfaceShader")
cmds.sets(plane, edit=True, forceElement=sg)

cam = cmds.camera(name="BG_CAM")[0]
shape = cmds.listRelatives(cam, shapes=True, fullPath=True)[0]
cmds.setAttr(shape + ".renderable", 1)
for s in cmds.ls(type="camera", long=True):
    if s != shape:
        cmds.setAttr(s + ".renderable", 0)
if VARIANT == "ortho":
    cmds.setAttr(shape + ".orthographic", 1)
    cmds.setAttr(shape + ".horizontalFilmAperture", 1.417)
    cmds.setAttr(shape + ".verticalFilmAperture", 1.417 * H / W)
    cmds.setAttr(shape + ".filmFit", 1)
    # the plane shows 6000 source px over 60 units: 1920 render px = 19.2 units
    cmds.setAttr(shape + ".orthographicWidth", 19.2)
    cmds.setAttr(cam + ".tz", 50)
else:
    hfa, vfa, fit = (1.417, 1.417 * H / W, 1) if VARIANT == "persp" else (1.417, 0.945, 0)
    cmds.setAttr(shape + ".horizontalFilmAperture", hfa)
    cmds.setAttr(shape + ".verticalFilmAperture", vfa)
    cmds.setAttr(shape + ".filmFit", fit)
    cmds.setAttr(shape + ".focalLength", 35.0)
    dist = 19.2 * 35.0 / (hfa * 25.4)                 # 1920 px across = 19.2 units on the plane
    if VARIANT == "persp32":
        # a camera that is not at the origin: plane and camera moved and rotated together
        grp = cmds.group(empty=True, name="layout")
        cmds.parent(plane, grp)
        cmds.setAttr(cam + ".tz", dist)
        cam = cmds.parent(cam, grp)[0]
        shape = cmds.listRelatives(cam, shapes=True, fullPath=True)[0]
        cmds.setAttr(grp + ".rotateY", 30)
        cmds.setAttr(grp + ".rotateX", -10)
        cmds.setAttr(grp + ".translate", 12, 3, -7)
    else:
        cmds.setAttr(cam + ".tz", dist)
    cmds.setAttr(shape + ".farClipPlane", 1000)

render = maya_pm.render_data()
bg = maya_pm.bg_plane_data(plane, 6000, 4000)
cam_data = maya_pm.camera_data(shape)
print("camera problems:", pm.check_camera(cam_data, render))
print("bg corners:", bg["top_left"], bg["top_right"], bg["bottom_left"])
base = pm.maya_source_to_render(cam_data, render, bg)
print("base map: scale %.6f, translate (%.4f, %.4f)" % (base[0][0], base[0][2], base[1][2]))

# AE: 6000 x 4000 BG layer in a 1920 x 1080 comp; the AE layer's anchor is the image center.
# Its scale must match Maya's: the plane shows 6000 px over 60 units and 19.2 units fill 1920 px -> 1.
POSITIONS = [(960.0, 540.0), (960.0 + 1234.0, 540.0 - 777.0), (960.0 + 0.5, 540.0 + 0.5),
             (960.0 - 300.25, 540.0 + 120.75), (960.0 + 2000.0, 540.0 + 1300.0)]
METHODS = ["film_translate"] if VARIANT == "ortho" else list(pm.METHODS)
markers = testgrid.marker_positions(6000, 4000)
results = []
for method in METHODS:
    for (ax_, ay_) in POSITIONS:
        layer = {"position": [ax_, ay_], "anchorPoint": [3000.0, 2000.0], "scale": [100.0, 100.0], "rotation": 0}
        m_ae, _ = pm.ae_layer_matrix(layer)
        for key in maya_pm.CAMERA_ATTRS:                                  # back to a clean camera
            cmds.setAttr(shape + "." + maya_pm.CAMERA_ATTRS[key],
                         1.0 if key in ("zoom", "pre_scale", "post_scale") else 0)
        solved = pm.solve(method, maya_pm.camera_data(shape), render, bg, m_ae,
                          {"width": W, "height": H, "pixelAspect": 1.0})
        maya_pm.apply_values(shape, solved["values"])
        name = "e2e_%s_%s_%s_%g_%g" % (VARIANT, RENDERER, method, ax_, ay_)
        cmds.setAttr("defaultRenderGlobals.imageFilePrefix", name, type="string")
        if RENDERER == "sw":
            cmds.setAttr("defaultRenderGlobals.currentRenderer", "mayaSoftware", type="string")
            path = cmds.render(shape, x=W, y=H)
        else:
            cmds.setAttr("defaultRenderGlobals.currentRenderer", "mayaHardware2", type="string")
            path = cmds.ogsRender(camera=shape, width=W, height=H)
        img = png.read(path)
        expected = []
        for mk in markers:
            x, y = pm.apply(m_ae, mk["x"], mk["y"])            # where AE shows this source position
            expected.append(dict(mk, x=x, y=y))
        rep = measure.compare(img, expected, search=12, threshold=24)
        print("RESULT %-58s %s" % (name, measure.summary(rep)))
        results.append({"case": name, "values": solved["values"], "report": {k: v for k, v in rep.items()
                                                                              if k != "points"}})
with open(os.path.join(OUT, "e2e_%s_%s.json" % (VARIANT, RENDERER)), "w") as f:
    json.dump(results, f, indent=1, default=str)
