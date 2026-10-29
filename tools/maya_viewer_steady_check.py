"""mayapy: the viewer's steady view (D-48).

    mayapy tools/maya_viewer_steady_check.py <out folder>

Run with MAYA_APP_DIR set to a scratch folder.
1. A Maya layer whose dedicated camera has keys on film translate, post-scale and roll (a pivot, both roll
   orders) and its own 2D pan / zoom; the viewer camera zoomed out and panned, the view 2:1.
2. At every frame, the view (core view_affine, from the cameras as Maya evaluates them) is the same as
   without the motion: the expression's film translate is core.stack_view.steady_translate's.
3. The viewer camera moved to another layer keeps it; saving writes no node of ours; remove() leaves none.
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
from syncbridge.core import stack_view as sv  # noqa: E402
from syncbridge_maya import cleanup, layer_mapping, pixel_mapping, viewer_camera  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
os.makedirs(OUT, exist_ok=True)
VIEW = (1200.0, 600.0)
TOL = 1e-6                  # some camera attributes are single precision (about 4e-8 seen)
checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print("%s  %s  %s" % ("OK" if ok else "NG", name, detail))


def shape_of(tr):
    return cmds.listRelatives(tr, shapes=True, fullPath=True)[0]


def key(shape, attr, values):
    for frame, value in values:
        cmds.setKeyframe(shape, attribute=attr, time=frame, value=value)


def worst_over_frames(ded, viewer, frames):
    """The largest difference to the view without the motion, and to the view at the first frame."""
    worst = drift = 0.0
    first = None
    for frame in frames:
        cmds.currentTime(frame)
        e, v = pixel_mapping.camera_data(ded), pixel_mapping.camera_data(viewer)
        got = sv.view_affine(e, v, *VIEW)
        want = sv.view_affine(sv.unmoved(e), sv.unmoved(v), *VIEW)
        worst = max([worst] + [abs(a - b) for a, b in zip(got, want)])
        first = first or got
        drift = max([drift] + [abs(a - b) for a, b in zip(got, first)])
    return worst, drift


cmds.file(new=True, force=True)
cam = cmds.camera(name="SHOT_CAM")[0]
cmds.select(cam)
layer_mapping.add_layer("BG")
ded = shape_of(cleanup.dedicated_cameras()[0])
key(ded, "filmTranslateH", [(1, 0.0), (10, 0.3)])
key(ded, "filmTranslateV", [(1, 0.1), (10, -0.2)])
key(ded, "postScale", [(1, 1.0), (10, 1.4)])
key(ded, "filmRollValue", [(1, 0.0), (10, 25.0)])
cmds.setAttr(ded + ".horizontalRollPivot", 0.1)
cmds.setAttr(ded + ".verticalRollPivot", -0.05)
cmds.setAttr(ded + ".panZoomEnabled", True)
cmds.setAttr(ded + ".horizontalPan", 0.03)
cmds.setAttr(ded + ".zoom", 0.9)

viewer = viewer_camera.ensure(ded, initial_zoom=1.2)
viewer_camera.set_view_aspect(VIEW[0] / VIEW[1], viewer)
viewer_camera.set_view(viewer, 0.08, -0.04, 1.3)
frames = [1, 3.5, 7, 10]

worst, drift = worst_over_frames(ded, viewer, frames)
check("steady (Rotate-Translate)", worst < TOL and drift < TOL, "worst %.3g drift %.3g" % (worst, drift))
cmds.setAttr(ded + ".filmRollOrder", 1)
worst, drift = worst_over_frames(ded, viewer, frames)
check("steady (Translate-Rotate)", worst < TOL and drift < TOL, "worst %.3g drift %.3g" % (worst, drift))
for fit, name in ((1, "horizontal"), (2, "vertical"), (3, "overscan"), (0, "fill")):
    # (linked from the original camera to the dedicated one) the pan's units depend on the fit and the view
    cmds.setAttr(shape_of(cam) + ".filmFit", fit)
    worst, drift = worst_over_frames(ded, viewer, frames)
    check("steady (%s fit)" % name, worst < TOL and drift < TOL and cmds.getAttr(ded + ".filmFit") == fit,
          "worst %.3g drift %.3g" % (worst, drift))

cmds.currentTime(7)
v = pixel_mapping.camera_data(viewer)
expected = sv.steady_translate(dict(v, ft_h=cmds.getAttr(ded + ".filmTranslateH"),
                                    ft_v=cmds.getAttr(ded + ".filmTranslateV")), VIEW[0] / VIEW[1])
check("expression == core", abs(v["ft_h"] - expected[0]) < TOL and abs(v["ft_v"] - expected[1]) < TOL,
      "%s %s" % ((v["ft_h"], v["ft_v"]), expected))

viewer_camera.set_view(viewer, 0.0, 0.0, 1.0)
cmds.currentTime(7)
check("no view: the camera's own film translate",
      abs(cmds.getAttr(viewer + ".filmTranslateH") - cmds.getAttr(ded + ".filmTranslateH")) < TOL)

# another layer: the viewer camera moves there and follows that camera's motion
cmds.select(cam)
layer_mapping.add_layer("CHAR")
ded2 = [shape_of(c) for c in cleanup.dedicated_cameras() if shape_of(c) != ded][0]
key(ded2, "filmTranslateH", [(1, -0.2), (10, 0.25)])
viewer = viewer_camera.ensure(ded2)
viewer_camera.set_view(viewer, -0.05, 0.02, 1.25)
worst, drift = worst_over_frames(ded2, viewer, frames)
check("steady after moving to another layer", worst < TOL and drift < TOL,
      "worst %.3g drift %.3g" % (worst, drift))

path = os.path.join(OUT, "steady.ma")
cmds.file(rename=path)
cmds.file(save=True, type="mayaAscii", force=True)
with open(path, encoding="utf-8", errors="replace") as f:
    text = f.read()
check("saved file has no viewer node", not re.findall(r"SB_VIEWER\w*", text), str(re.findall(r"SB_VIEWER\w*", text)))

viewer_camera.remove()
left = cmds.ls("SB_VIEWER*") + cmds.ls(type="expression")
check("remove leaves nothing", not left, str(left))
check("dedicated cameras keep their keys", cmds.keyframe(ded + ".filmTranslateH", q=True, keyframeCount=True) == 2)

print("RESULT %s" % ("PASS" if all(checks) else "FAIL"))
