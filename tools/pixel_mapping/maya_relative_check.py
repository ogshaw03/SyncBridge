r"""Pixel Mapping relative mode check in Maya (D-25): a 3D BG at several depths and a camera with its own
camera work; the AE BG layer slides / scales from the reference; every depth must follow in 2D.

    "C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe" tools\pixel_mapping\maya_relative_check.py <out_dir> [method]

method: pan_zoom (default, also scales), film_roll (translate, scale and rotation), film_translate,
film_offset (refused here: the camera work keys the film offset). Hardware 2.0 (ogsRender). Three planes at different depths (near / mid / far) stand in
for a building / town model; each shows a part of the test grid at 1 texel = 1 render pixel, left /
center / right in the frame. The camera has keys (translateX and film offset: camera work).
The first send records the reference (frame 10); then the AE layer moves (and scales) and the camera is
rendered again. Markers must be where the reference view, moved by the AE change, puts them.
"""
import os
import sys

import maya.standalone
maya.standalone.initialize()
import maya.cmds as cmds

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path[:0] = [os.path.join(REPO, "src"), os.path.join(REPO, "maya_plugin", "scripts")]
from syncbridge.core import layer_mapping as core_lm
from syncbridge.core import pixel_mapping as pm
from syncbridge.pixelcheck import measure, png, testgrid
from syncbridge_maya import layer_mapping, pixel_mapping

OUT = sys.argv[1]
METHOD = sys.argv[2] if len(sys.argv) > 2 else "pan_zoom"
os.makedirs(OUT, exist_ok=True)
GRID = os.path.join(OUT, "testgrid_6000x4000.png").replace("\\", "/")
if not os.path.exists(GRID):
    png.write(GRID, testgrid.make(6000, 4000))
W, H = 1920, 1080
SRC_W, SRC_H = 6000, 4000
HFA, FOCAL, CAM_Z = 1.417, 35.0, 40.0
cmds.workspace(fileRule=["images", OUT])
for attr, value in (("width", W), ("height", H), ("deviceAspectRatio", float(W) / H), ("pixelAspect", 1.0)):
    cmds.setAttr("defaultResolution." + attr, value)
cmds.setAttr("defaultRenderGlobals.imageFormat", 32)
cmds.setAttr("hardwareRenderingGlobals.enableTextureMaxRes", False)
cmds.setAttr("defaultRenderGlobals.currentRenderer", "mayaHardware2", type="string")

shader = cmds.shadingNode("surfaceShader", asShader=True)
tex = cmds.shadingNode("file", asTexture=True)
cmds.setAttr(tex + ".fileTextureName", GRID, type="string")
cmds.connectAttr(tex + ".outColor", shader + ".outColor")
sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
cmds.connectAttr(shader + ".outColor", sg + ".surfaceShader")

# (name, plane z, screen center x px, source window left / top px); each window is 600 x 600 source px
WINDOW = 600.0
PLANES = [("near", 0.0, 340.0, 1000.0, 1000.0), ("mid", -60.0, 960.0, 2500.0, 1500.0),
          ("far", -400.0, 1580.0, 4000.0, 2000.0)]
planes = []
for name, z, screen_x, left, top in PLANES:
    depth = CAM_Z - z
    k = depth * (HFA * 25.4 / FOCAL) / W                    # world units per render pixel at this depth
    size = WINDOW * k
    p = cmds.polyPlane(name=name, w=size, h=size, sx=1, sy=1, ax=(0, 0, 1))[0]
    cmds.setAttr(p + ".translate", (screen_x - W / 2.0) * k, 0.0, z)
    # UVs: only this window of the source, so 1 texel = 1 render pixel
    u0, u1 = left / SRC_W, (left + WINDOW) / SRC_W
    v1, v0 = 1.0 - top / SRC_H, 1.0 - (top + WINDOW) / SRC_H
    cmds.polyEditUV(p + ".map[*]", scaleU=u1 - u0, scaleV=v1 - v0, pivotU=0.0, pivotV=0.0)
    cmds.polyEditUV(p + ".map[*]", u=u0, v=v0)
    cmds.sets(p, edit=True, forceElement=sg)
    planes.append({"name": name, "node": p, "z": z, "size": size, "left": left, "top": top,
                   "x": (screen_x - W / 2.0) * k})

cam = cmds.camera(name="SHOT_CAM")[0]
shape = cmds.listRelatives(cam, shapes=True, fullPath=True)[0]
cmds.setAttr(shape + ".horizontalFilmAperture", HFA)
cmds.setAttr(shape + ".verticalFilmAperture", 0.945)
cmds.setAttr(shape + ".filmFit", 0)
cmds.setAttr(shape + ".focalLength", FOCAL)
cmds.setAttr(shape + ".farClipPlane", 5000)
cmds.setAttr(shape + ".renderable", 1)
for s in cmds.ls(type="camera", long=True):
    if s != shape:
        cmds.setAttr(s + ".renderable", 0)
# camera work: a truck and a film offset drift (keys)
cmds.setKeyframe(cam, attribute="translateX", time=1, value=-0.5)
cmds.setKeyframe(cam, attribute="translateX", time=24, value=0.5)
cmds.setAttr(cam + ".tz", CAM_Z)
cmds.setKeyframe(shape, attribute="horizontalFilmOffset", time=1, value=0.0)
cmds.setKeyframe(shape, attribute="horizontalFilmOffset", time=24, value=0.02)
cmds.currentTime(10)


def info(position, scale=100.0, rotation=0.0):
    return {"comp": {"id": 1, "name": "c010", "width": W, "height": H, "pixelAspect": 1, "time": 0},
            "layer": {"id": 7, "name": "BG", "position": list(position), "anchorPoint": [3000, 2000],
                      "scale": [scale, scale], "rotation": rotation, "threeD": False, "parent": None, "effects": [],
                      "source": "bg", "source_width": SRC_W, "source_height": SRC_H}}


def render(name):
    cmds.setAttr("defaultRenderGlobals.imageFilePrefix", name, type="string")
    return png.read(cmds.ogsRender(camera=shape, width=W, height=H))


def marker_world_points():
    """World positions of the markers inside each plane's source window."""
    out = []
    for pl in planes:
        for mk in testgrid.marker_positions(SRC_W, SRC_H):
            fx = (mk["x"] - pl["left"]) / WINDOW
            fy = (mk["y"] - pl["top"]) / WINDOW
            if 0.05 < fx < 0.95 and 0.05 < fy < 0.95:
                world = (pl["x"] - pl["size"] / 2.0 + fx * pl["size"], pl["size"] / 2.0 - fy * pl["size"], pl["z"])
                out.append((pl["name"], mk, world))
    return out


def expected_now(points):
    cam_data = pixel_mapping.camera_data(shape)
    out = []
    for plane, mk, world in points:
        x, y = pm.project(cam_data, pixel_mapping.render_data(), pm.to_camera_space(cam_data["world_inverse"], world))
        out.append(dict(mk, id="%s_%s" % (plane, mk["id"]), x=x, y=y))
    return out


def per_depth(rep):
    by = {}
    for pt in rep["points"]:
        name = pt["id"].split("_")[0]
        by.setdefault(name, []).append(pt["dist"])
    return {k: "%d markers max %.3f" % (len(v), max(v)) for k, v in sorted(by.items())}


store = layer_mapping.store()                   # wire the AE layer as the layer map does (D-28)
maya_layer = core_lm.layer_for_camera(store, layer_mapping.uuid_of(shape), shape)
core_lm.connect(store, pixel_mapping._ae_layer(info((960.0, 540.0))), maya_layer["id"], METHOD, "relative")
layer_mapping.save_store(store)
points = marker_world_points()
r0 = pixel_mapping.apply_from_ae(info((960.0, 540.0)))
print("reference:", r0["status"], r0.get("reference_recorded"), r0["mapping"]["text"])
img0 = render("rel_%s_ref" % METHOD)
exp0 = expected_now(points)
rep0 = measure.compare(img0, exp0, search=12, threshold=24)
print("RESULT reference render vs camera model: %s | %s" % (measure.summary(rep0), per_depth(rep0)))

CASES = [((1083.25, 492.5), 100.0, 0.0), ((700.0, 610.75), 100.0, 0.0)]
if METHOD in ("pan_zoom", "film_roll"):
    CASES.append(((1000.0, 520.0), 110.0, 0.0))
if METHOD == "film_roll":
    # the user's cases (2026-10-25): 42 degrees and 170 %
    CASES += [((960.0, 540.0), 100.0, 42.0), ((960.0, 540.0), 170.0, 0.0), ((1010.0, 500.0), 130.0, -12.5)]
ref_m, _ = pm.ae_layer_matrix(info((960.0, 540.0))["layer"])
for position, scale, rotation in CASES:
    try:
        r = pixel_mapping.apply_from_ae(info(position, scale, rotation))
    except ValueError as exc:
        print("RESULT %-14s AE %s scale %g%% rot %g: refused: %s" % (METHOD, position, scale, rotation, exc))
        continue
    cur_m, _ = pm.ae_layer_matrix(info(position, scale, rotation)["layer"])
    change = pm.multiply(cur_m, pm.invert(ref_m))
    img = render("rel_%s_%g_%g_%g_%g" % (METHOD, position[0], position[1], scale, rotation))
    moved = []
    for e in exp0:
        x, y = pm.apply(change, e["x"], e["y"])
        moved.append(dict(e, x=x, y=y))
    rep = measure.compare(img, moved, search=12, threshold=24)
    print("RESULT %-14s AE %s scale %g%% rot %g: %s | %s | camera work film offset untouched: %s" % (
        METHOD, position, scale, rotation, measure.summary(rep), per_depth(rep), "hfo" not in r["values"]))
