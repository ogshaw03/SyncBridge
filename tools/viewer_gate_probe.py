"""Which camera draws Maya's resolution gate in the SyncBridge viewer? Read-only: run in the user's Maya, with the
viewer open. Writes probe_results/viewer_gate_probe.txt and changes nothing in the scene.

    exec(open(r"E:\\OG_Tools\\SyncBridge\\tools\\viewer_gate_probe.py", encoding="utf-8").read())
"""
import os

from maya import cmds

GATE_ATTRS = ("displayResolution", "displayFilmGate", "displayGateMask", "overscan", "panZoomEnabled",
              "horizontalPan", "verticalPan", "zoom")


def _probe(out):
    out.append("maya %s" % cmds.about(version=True))
    for name in ("syncbridge_layer_stack.py", "syncbridge_guide.py"):
        out.append("plug-in %s loaded %s" % (name, cmds.pluginInfo(name, q=True, loaded=True)))
    try:
        import syncbridge_maya.viewer_window as vw
        window = vw._window
        out.append("viewer code has the solo fit (D-52): %s" % hasattr(vw.ViewerWindow, "_fit_solo"))
        out.append("viewer code follows the view widget (D-51): %s" % hasattr(vw.ViewerWindow, "_follow_view_widget"))
        if window is not None and window.panel:
            out.append("viewer panel %s camera %s" % (window.panel, cmds.modelEditor(window.panel, q=True, camera=True)))
            out.append("override %s" % cmds.modelEditor(window.panel, q=True, rendererOverrideName=True))
    except Exception as exc:
        out.append("viewer: %s" % exc)
    for panel in cmds.getPanel(type="modelPanel") or []:
        out.append("panel %s camera %s" % (panel, cmds.modelEditor(panel, q=True, camera=True)))
    guides = cmds.ls(type="syncBridgeCompGuide") if "syncBridgeCompGuide" in (cmds.allNodeTypes() or []) else []
    out.append("comp guides %s" % guides)
    for shape in cmds.ls(type="camera", long=True) or []:
        values = ["%s=%s" % (a, cmds.getAttr("%s.%s" % (shape, a))) for a in GATE_ATTRS]
        out.append("%s | %s" % (shape, " ".join(values)))


def _main():
    out = []
    try:
        _probe(out)
    except Exception as exc:
        out.append("probe stopped: %s" % exc)
    here = globals().get("__file__") or r"E:\OG_Tools\SyncBridge\tools\viewer_gate_probe.py"
    folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(here))), "probe_results")
    if not os.path.isdir(folder):
        os.makedirs(folder)
    path = os.path.join(folder, "viewer_gate_probe.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("SyncBridge: wrote %s" % path)


_main()
