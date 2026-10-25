"""mayapy: the comp frame the layer stack's HUD draws (D-34, H-MY-36).

    mayapy tools/pixel_mapping/maya_stack_frame_check.py

The plug-in's frame_screen_points (core.view_frame.frame_rect) must put a frame of the render's own
size exactly on the render area that Maya's frustums give (getViewingFrustum without overscan: the stack
draws at overscan 1.0 whatever the camera says, D-34 /
getRenderingFrustum), for each Film Fit, view and render aspect, camera overscan and comp size, also when the
camera has a film translate / film offset / pan (they move the picture, not the frame). The shade
bands and the inside cover the view once. Allowed: 0.01 px (deviceAspectRatio is a float).
"""
import importlib.util
import itertools
import os
import sys

import maya.standalone
maya.standalone.initialize()
import maya.cmds as cmds  # noqa: E402
import maya.api.OpenMaya as om  # noqa: E402

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
spec = importlib.util.spec_from_file_location(
    "sb_layer_stack_plugin", os.path.join(REPO, "maya_plugin", "plug-ins", "syncbridge_layer_stack.py"))
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)
plugin._import_core(os.path.join(REPO, "maya_plugin", "plug-ins"))

cmds.file(new=True, force=True)
tr, shape = cmds.camera()
sel = om.MSelectionList()
sel.add(shape)
path = sel.getDagPath(0)
fn = om.MFnCamera(path)
worst, cases = 0.0, 0
for fit, (hfa, vfa), (rw, rh), (vw, vh), overscan, scale, shifted in itertools.product(
        (0, 1, 2, 3), ((1.417, 0.945), (0.98, 0.735)), ((1920, 1080), (2048, 858), (1080, 1350)),
        ((1200, 600), (800, 700)), (1.0, 1.3), (1.0, 0.5), (False, True)):
    for attr, value in (("horizontalFilmAperture", hfa), ("verticalFilmAperture", vfa), ("filmFit", fit),
                        ("overscan", overscan), ("filmTranslateH", 0.2 if shifted else 0.0),
                        ("horizontalFilmOffset", 0.05 if shifted else 0.0), ("panZoomEnabled", shifted),
                        ("horizontalPan", 0.1 if shifted else 0.0)):
        cmds.setAttr("%s.%s" % (shape, attr), value)
    cmds.setAttr("defaultResolution.width", rw)
    cmds.setAttr("defaultResolution.height", rh)
    cmds.setAttr("defaultResolution.deviceAspectRatio", float(rw) / rh)
    vl, vr, vb, vt = fn.getViewingFrustum(float(vw) / vh, False, True, False)   # the stack ignores overscan
    comp = {"width": int(rw * scale), "height": int(rh * scale), "name": ""}
    points, _ = plugin.frame_screen_points(path, comp, (0, 0, vw, vh))
    rl, rr, rb, rt = fn.getRenderingFrustum(float(rw) / rh)
    fx, fy = comp["width"] / float(rw), comp["height"] / float(rh)
    cx, cy = (rl + rr) / 2.0, (rb + rt) / 2.0
    hw, hh = (rr - rl) / 2.0 * fx, (rt - rb) / 2.0 * fy
    expect = [(cx + sx * hw, cy + sy * hh) for sx, sy in ((-1, 1), (1, 1), (1, -1), (-1, -1))]
    expect_px = [((x - vl) / (vr - vl) * vw, (y - vb) / (vt - vb) * vh) for x, y in expect]
    ours = sorted((round(p.x, 6), round(p.y, 6)) for p in points)
    theirs = sorted((round(x, 6), round(y, 6)) for x, y in expect_px)
    diff = max(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(ours, theirs))
    if diff > 1e-2:
        print("DIFF fit %d film %s render %s view %s overscan %g scale %g shifted %s: %s vs %s"
              % (fit, (hfa, vfa), (rw, rh), (vw, vh), overscan, scale, shifted, ours, theirs))
    worst = max(worst, diff)
    cases += 1
    bands = plugin.mask_bands(points, (0, 0, vw, vh))
    xs, ys = [p.x for p in points], [p.y for p in points]
    inside = max(0.0, min(max(xs), vw) - max(min(xs), 0)) * max(0.0, min(max(ys), vh) - max(min(ys), 0))
    covered = inside + sum((r - l) * (t - b) for l, b, r, t in bands)
    if abs(covered - vw * vh) > (vw + vh) * 2 * 0.5:          # bands under 0.5 px are not drawn
        print("MASK fit %d render %s view %s overscan %g scale %g: covered %.3f of %d" % (
            fit, (rw, rh), (vw, vh), overscan, scale, covered, vw * vh))
        worst = max(worst, 1.0)
print("cases %d, max diff %.2e px" % (cases, worst))
print("RESULT", "PASS" if worst < 1e-2 else "FAIL")
maya.standalone.uninitialize()
os._exit(0)
