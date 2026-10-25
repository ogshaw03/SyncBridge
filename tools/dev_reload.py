"""Development: what the "SB Dev" shelf button runs (tools/dev_maya_shelf.py). Kept in the repository so
a change here needs no new shelf button.

Closes the open SyncBridge windows, puts the views using the layer stack back to Viewport 2.0, unloads
the plug-in (loaded again with the new code when used), drops the syncbridge* modules and opens the
panel from this repository.
"""
import sys

from maya import cmds

try:
    from PySide6 import QtWidgets
except ImportError:
    from PySide2 import QtWidgets

SCRIPTS = __file__.replace("\\", "/").rsplit("/tools/", 1)[0] + "/maya_plugin/scripts"
WINDOWS = ("SyncBridgePanel", "SyncBridgeLayerMap", "SyncBridgeViewer")


def _close_windows():
    # Find first, then close: closing the viewer deletes its model panel's menus, which are top level
    # widgets too ("Internal C++ object (QMenu) already deleted" while looping, the user, 2026-10-25).
    found = []
    for w in QtWidgets.QApplication.topLevelWidgets():
        try:
            if w.objectName() in WINDOWS:
                found.append(w)
        except RuntimeError:          # deleted by Qt meanwhile
            pass
    for w in found:
        try:
            w.close()
            w.deleteLater()
        except RuntimeError:
            pass


def main():
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    _close_windows()
    for p in cmds.getPanel(type="modelPanel") or []:
        try:
            if cmds.modelEditor(p, q=True, rendererOverrideName=True) == "SyncBridgeLayerStack":
                cmds.modelEditor(p, e=True, rendererOverrideName="")
        except RuntimeError:
            pass
    if cmds.pluginInfo("syncbridge_layer_stack.py", q=True, loaded=True):
        cmds.unloadPlugin("syncbridge_layer_stack.py")
    for name in [n for n in sys.modules if n.split(".")[0] in ("syncbridge", "syncbridge_maya")]:
        del sys.modules[name]
    import syncbridge_maya.ui
    syncbridge_maya.ui.show()
    print("SyncBridge (dev): reloaded from " + SCRIPTS)


main()
