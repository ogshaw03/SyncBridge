"""A wide BG plate for testing the source camera mode (D-39) (GUI Maya, Script Editor, Python tab).

    exec(open(r"<repository>/tools/pixel_mapping/make_test_plate.py", encoding="utf-8").read())

1. Look through the BG camera (the camera that will be the BG layer's camera; pull it back or widen its
   film back for a wider view). Optionally select the BG objects: then only they are rendered.
2. Run: one Hardware 2.0 render of the current frame through the current view's camera, at SCALE times
   the scene's render resolution, saved as a PNG where you choose (a file dialog).
The camera is not changed. What is changed for the render (resolution, image format, prefix,
lodVisibility) is put back afterwards, outside the undo. Keep the camera as it is after this.
Use the PNG at 100 % in the AE comp and make that camera the BG Maya layer's camera (source camera mode).
"""
import os
import shutil

from maya import cmds

SCALE = 2                # the plate's size = SCALE x the scene's render resolution


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


def _keep_shapes():
    """Geometry shapes under the selection (none selected: None = render everything)."""
    selected = cmds.ls(selection=True, long=True) or []
    if not selected:
        return None
    shapes = cmds.listRelatives(selected, allDescendents=True, type="geometryShape", fullPath=True) or []
    shapes += cmds.ls(selected, type="geometryShape", long=True) or []
    return set(shapes)


def _others_hidden(keep):
    """lodVisibility off for every geometry shape not in `keep` (not recorded for undo; the caller
    restores). Returns (shapes turned off, shapes that could not be: locked or driven)."""
    hidden, skipped = [], []
    for shape in cmds.ls(type="geometryShape", long=True, noIntermediate=True) or []:
        if shape in keep or not cmds.getAttr(shape + ".lodVisibility"):
            continue
        plug = shape + ".lodVisibility"
        if cmds.getAttr(plug, lock=True) or cmds.listConnections(plug, source=True, destination=False):
            skipped.append(shape)
            continue
        cmds.setAttr(plug, False)
        hidden.append(shape)
    return hidden, skipped


def render_plate(camera, path, keep=None):
    """One Hardware 2.0 render at SCALE x the render resolution as a PNG, copied to `path`."""
    res = ("width", "height", "deviceAspectRatio", "pixelAspect")
    saved = {"imageFormat": cmds.getAttr("defaultRenderGlobals.imageFormat"),
             "imageFilePrefix": cmds.getAttr("defaultRenderGlobals.imageFilePrefix") or ""}
    saved_res = dict((a, cmds.getAttr("defaultResolution." + a)) for a in res)
    width, height = saved_res["width"] * SCALE, saved_res["height"] * SCALE
    undo_on = cmds.undoInfo(query=True, state=True)
    hidden, skipped = [], []
    cmds.undoInfo(stateWithoutFlush=False)
    try:
        if keep is not None:
            hidden, skipped = _others_hidden(keep)
        cmds.setAttr("defaultResolution.width", width)
        cmds.setAttr("defaultResolution.height", height)
        cmds.setAttr("defaultRenderGlobals.imageFormat", 32)                    # PNG
        cmds.setAttr("defaultRenderGlobals.imageFilePrefix", "syncbridge_test_plate", type="string")
        rendered = cmds.ogsRender(camera=camera, width=width, height=height)
    finally:
        for shape in hidden:
            cmds.setAttr(shape + ".lodVisibility", True)
        for a in res:
            cmds.setAttr("defaultResolution." + a, saved_res[a])
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
    keep = _keep_shapes()
    files = cmds.fileDialog2(caption="Save the BG plate (PNG)", fileFilter="PNG (*.png)", fileMode=0,
                             startingDirectory=os.path.join(os.path.expanduser("~"), "Documents"))
    if not files:
        print("Cancelled.")
        return None
    path = files[0] if files[0].lower().endswith(".png") else files[0] + ".png"
    out, size = render_plate(camera, path, keep)
    print("BG plate through %s (%s): %dx%d PNG: %s" % (
        camera.split("|")[-1], "selected objects only" if keep is not None else "everything visible",
        size[0], size[1], out))
    print("Keep %s as it is now; make it the BG Maya layer's camera (source camera mode)." % camera.split("|")[-1])
    return out


if __name__ == "__main__":
    main()
