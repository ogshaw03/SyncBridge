"""SyncBridge viewer diagnosis (D-44): run in Maya's Script Editor (Python) while the viewer is open.

    exec(open(r"<repository>/tools/viewer_diagnose.py", encoding="utf-8").read())

Prints the editing layer, its dedicated camera and the viewer camera (the 2D values and what drives
them), and what the plug-in was handed. Changes nothing.
"""
from maya import cmds

ATTRS = ("focalLength", "horizontalFilmAperture", "verticalFilmAperture", "filmFit", "overscan", "cameraScale",
         "lensSqueezeRatio", "horizontalFilmOffset", "verticalFilmOffset", "panZoomEnabled", "renderPanZoom",
         "horizontalPan", "verticalPan", "zoom", "preScale", "postScale", "filmTranslateH", "filmTranslateV",
         "filmRollValue", "filmRollOrder", "orthographic")


def _report():
    import __main__
    from syncbridge_maya import layer_stack, viewer_camera
    state = getattr(__main__, layer_stack.STATE_KEY, None) or {}
    print("=== SyncBridge viewer diagnosis ===")
    print("frame: %s" % cmds.currentTime(q=True))
    print("plug-in: %s" % [p for p in (cmds.pluginInfo(q=True, listPlugins=True) or []) if "syncbridge" in p.lower()])
    print("state: version %s, margin %s, editing %s" % (state.get("version"), state.get("margin"), state.get("editing")))
    print("layers handed to the plug-in (bottom first): %s" % [(n, c) for n, c, _ in state.get("layers") or []])
    for panel in cmds.getPanel(type="modelPanel") or []:
        if cmds.modelEditor(panel, q=True, rendererOverrideName=True) == layer_stack.OVERRIDE_NAME:
            print("panel %s looks through %s (renderer %s)" % (
                panel, cmds.modelEditor(panel, q=True, camera=True),
                cmds.modelEditor(panel, q=True, rendererOverrideName=True)))
    view = viewer_camera.current()
    dedicated = viewer_camera.followed(view) if view else None
    cams = [("dedicated", dedicated), ("viewer", view)]
    if dedicated:
        original = cmds.listRelatives(cmds.listRelatives(dedicated, parent=True, fullPath=True)[0], parent=True,
                                      fullPath=True)
        if original:
            shapes = cmds.listRelatives(original[0], shapes=True, type="camera", fullPath=True) or []
            cams.insert(0, ("original", shapes[0] if shapes else None))
    print("%-24s" % "attribute" + "".join("%-16s" % name for name, _ in cams))
    for attr in ATTRS:
        row = "%-24s" % attr
        for _, cam in cams:
            row += "%-16s" % (("%.6g" % cmds.getAttr("%s.%s" % (cam, attr))) if cam else "-")
        print(row)
    if view:
        print("viewer camera inputs:")
        for attr in ATTRS:
            src = cmds.listConnections("%s.%s" % (view, attr), source=True, destination=False, plugs=True)
            if src:
                print("  %s <- %s" % (attr, src[0]))
        tr = cmds.listRelatives(view, parent=True, fullPath=True)[0]
        print("viewer transform: t %s r %s s %s" % (cmds.getAttr(tr + ".translate")[0], cmds.getAttr(tr + ".rotate")[0],
                                                    cmds.getAttr(tr + ".scale")[0]))
    print("=== end ===")


_report()
