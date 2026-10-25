"""A stand-in character for testing the layer map / viewer (GUI Maya, Script Editor, Python tab).

    exec(open(r"<repository>/tools/pixel_mapping/make_test_char.py", encoding="utf-8").read())

1. A sphere (red, Lambert) in the middle of the current view's camera, DISTANCE units in front of it.
2. One Hardware 2.0 render of the current frame at the scene's render resolution, through that
   camera, of the sphere only (the other shapes' lodVisibility is off during the render), background
   transparent (alpha), saved as a PNG where you choose (a file dialog).
What is changed for it (image format, prefix, lodVisibility) is put back afterwards, outside the undo.
Use the PNG as the CHAR layer in AE (scale 100 %, in the middle of the comp), and a Maya layer with
the same camera and the sphere as its object.
"""
import os
import shutil

from maya import cmds

DISTANCE = 15.0          # in front of the camera (scene units)
RADIUS = 1.5


def _view_camera():
    """The camera of the view with the focus (or the first visible model panel), as its transform."""
    panels = [cmds.getPanel(withFocus=True)] + (cmds.getPanel(visiblePanels=True) or [])
    for panel in panels:
        if panel and cmds.getPanel(typeOf=panel) == "modelPanel":
            cam = cmds.modelPanel(panel, query=True, camera=True)
            if cmds.nodeType(cam) == "camera":
                cam = cmds.listRelatives(cam, parent=True, fullPath=True)[0]
            return cmds.ls(cam, long=True)[0]
    raise RuntimeError("No model panel: click a view first.")


def make_sphere(camera):
    """A red sphere DISTANCE in front of the camera, on its view axis (-Z of the camera)."""
    m = cmds.xform(camera, query=True, worldSpace=True, matrix=True)
    pos = [m[12] - m[8] * DISTANCE, m[13] - m[9] * DISTANCE, m[14] - m[10] * DISTANCE]
    sphere = cmds.polySphere(name="testChar", radius=RADIUS, subdivisionsX=32, subdivisionsY=16)[0]
    cmds.xform(sphere, worldSpace=True, translation=pos)
    shader = cmds.shadingNode("lambert", asShader=True, name="testChar_mat")
    cmds.setAttr(shader + ".color", 0.85, 0.2, 0.15, type="double3")
    sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=shader + "SG")
    cmds.connectAttr(shader + ".outColor", sg + ".surfaceShader")
    cmds.sets(sphere, edit=True, forceElement=sg)
    return sphere


def _others_hidden(keep):
    """Turn off lodVisibility of every other geometry shape for the render (ogsRender draws all that is
    visible: the BG was in the first version's PNG, the user, 2026-10-25). Not recorded for undo; the
    caller restores. Returns (shapes turned off, shapes that could not be: locked or driven)."""
    keep_shapes = set(cmds.listRelatives(keep, shapes=True, fullPath=True) or [])
    hidden, skipped = [], []
    for shape in cmds.ls(type="geometryShape", long=True, noIntermediate=True) or []:
        if shape in keep_shapes or not cmds.getAttr(shape + ".lodVisibility"):
            continue
        plug = shape + ".lodVisibility"
        if cmds.getAttr(plug, lock=True) or cmds.listConnections(plug, source=True, destination=False):
            skipped.append(shape)
            continue
        cmds.setAttr(plug, False)
        hidden.append(shape)
    return hidden, skipped


def render_png(camera, path, only=None):
    """One Hardware 2.0 render (ogsRender: it writes a file in the GUI and in mayapy alike) as a PNG with
    alpha, copied to `path`; with `only`, nothing else is drawn. The changed settings are restored."""
    saved = {"imageFormat": cmds.getAttr("defaultRenderGlobals.imageFormat"),
             "imageFilePrefix": cmds.getAttr("defaultRenderGlobals.imageFilePrefix") or ""}
    undo_on = cmds.undoInfo(query=True, state=True)
    hidden, skipped = [], []
    cmds.undoInfo(stateWithoutFlush=False)
    try:
        if only:
            hidden, skipped = _others_hidden(only)
        cmds.setAttr("defaultRenderGlobals.imageFormat", 32)                    # PNG (with alpha)
        cmds.setAttr("defaultRenderGlobals.imageFilePrefix", "syncbridge_test_char", type="string")
        width = cmds.getAttr("defaultResolution.width")
        height = cmds.getAttr("defaultResolution.height")
        rendered = cmds.ogsRender(camera=camera, width=width, height=height)
    finally:
        for shape in hidden:
            cmds.setAttr(shape + ".lodVisibility", True)
        cmds.setAttr("defaultRenderGlobals.imageFormat", saved["imageFormat"])
        cmds.setAttr("defaultRenderGlobals.imageFilePrefix", saved["imageFilePrefix"], type="string")
        cmds.undoInfo(stateWithoutFlush=undo_on)
    if skipped:
        print("Not hidden (lodVisibility locked or driven), they may be in the PNG: %s"
              % ", ".join(s.split("|")[-1] for s in skipped))
    shutil.copyfile(rendered, path)
    return path, (width, height)


def main():
    camera = _view_camera()
    files = cmds.fileDialog2(caption="Save the test character (PNG)", fileFilter="PNG (*.png)", fileMode=0,
                             startingDirectory=os.path.join(os.path.expanduser("~"), "Documents"))
    if not files:
        print("Cancelled.")
        return None
    path = files[0] if files[0].lower().endswith(".png") else files[0] + ".png"
    sphere = make_sphere(camera)
    out, size = render_png(camera, path, only=sphere)
    cmds.select(sphere, replace=True)
    print("Test character: %s at the middle of %s; %dx%d PNG with alpha: %s" % (
        sphere, camera.split("|")[-1], size[0], size[1], out))
    return out


if __name__ == "__main__":
    main()
