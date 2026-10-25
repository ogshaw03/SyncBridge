"""mayapy: the viewer's margin projection (D-35).

    mayapy tools/pixel_mapping/maya_stack_margin_check.py

With margin 1 the plug-in's projection (core.stack_view from the camera read by model_camera) must put
points where Maya's own viewing frustum does (getViewingFrustum with pan / zoom, film offset), for each
Film Fit and view aspect; with a margin k they must sit at 1 / k of that around the view's center.
Film translate / scale / roll are not in Maya's frustum: they come from core.pixel_mapping.project, which
the renders confirmed (H-PM-8), and are checked in the GUI.
"""
import importlib.util
import itertools
import os

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
sv = plugin.core_view


def ndc(rows, p):
    row = (p[0], p[1], p[2], 1.0)
    c = [sum(row[i] * rows[i * 4 + j] for i in range(4)) for j in range(4)]
    return c[0] / c[3], c[1] / c[3]


cmds.file(new=True, force=True)
tr, shape = cmds.camera()
sel = om.MSelectionList()
sel.add(shape)
path = sel.getDagPath(0)
fn = om.MFnCamera(path)
points = [(0.3, -0.2, -2.0), (-1.5, 0.7, -9.0), (4.0, 2.5, -30.0)]
worst, cases = 0.0, 0
for fit, (hfa, vfa), (vw, vh), (hfo, vfo), (pan, hpan, vpan, zoom), margin in itertools.product(
        (0, 1, 2, 3), ((1.417, 0.945), (0.98, 0.735)), ((1200, 600), (800, 700)), ((0.0, 0.0), (0.05, -0.03)),
        ((False, 0.0, 0.0, 1.0), (True, 0.1, -0.04, 0.8)), (1.0, 1.2)):
    for attr, value in (("horizontalFilmAperture", hfa), ("verticalFilmAperture", vfa), ("filmFit", fit),
                        ("horizontalFilmOffset", hfo), ("verticalFilmOffset", vfo), ("panZoomEnabled", pan),
                        ("horizontalPan", hpan), ("verticalPan", vpan), ("zoom", zoom)):
        cmds.setAttr("%s.%s" % (shape, attr), value)
    near, far = fn.nearClippingPlane, fn.farClippingPlane
    l, r, b, t = fn.getViewingFrustum(float(vw) / vh, False, True, True)
    cam = plugin.model_camera(path)
    rows = sv.projection_rows(sv.ndc_affine(cam, vw, vh, margin), None, near, far)
    for x, y, z in points:
        u, v = x / -z * near, y / -z * near                      # on the near plane
        theirs = ((2 * u - (r + l)) / (r - l), (2 * v - (t + b)) / (t - b))
        ours = ndc(rows, (x, y, z))
        diff = max(abs(ours[0] - theirs[0] / margin), abs(ours[1] - theirs[1] / margin)) * max(vw, vh) / 2.0
        if diff > 1e-3:
            print("DIFF fit %d film %s view %s offset %s pan %s margin %g point %s: ours %s maya/m %s" % (
                fit, (hfa, vfa), (vw, vh), (hfo, vfo), (pan, hpan, vpan, zoom), margin, (x, y, z),
                [round(v_, 5) for v_ in ours], [round(v_ / margin, 5) for v_ in theirs]))
        worst = max(worst, diff)
    cases += 1
print("cases %d, max diff %.2e px" % (cases, worst))
print("RESULT", "PASS" if worst < 1e-3 else "FAIL")
maya.standalone.uninitialize()
os._exit(0)
