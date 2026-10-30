"""Template of a Maya GUI check (docs/VERIFICATION.md 3): copy it to the scratch folder and fill in SETUP and
STEPS. Maya builds a scene, runs the steps one by one on a timer (the UI draws between them), grabs the
screen, writes a log, then quits.

Started by maya.exe -script <a .mel that exec's this file> with these environment variables:
    MAYA_APP_DIR   a scratch folder (the user's prefs and shelves are never touched)
    SB_GUI_OUT     the folder for log.txt, script_editor.txt and the .png grabs
    SB_REPO        the repository (E:/OG_Tools/SyncBridge)
"""
import os
import sys
import traceback

OUT = os.environ["SB_GUI_OUT"]
REPO = os.environ["SB_REPO"]
LOG = open(os.path.join(OUT, "log.txt"), "w", encoding="utf-8")
STEP_MS = 1500                     # between steps: Maya draws and Qt handles its events


def log(*args):
    LOG.write(" ".join(str(a) for a in args) + "\n")
    LOG.flush()


try:
    sys.path[:0] = [os.path.join(REPO, "src"), os.path.join(REPO, "maya_plugin", "scripts")]
    from maya import cmds
    import maya.api.OpenMayaUI as omui2
    try:
        from PySide2 import QtCore, QtWidgets
    except ImportError:
        from PySide6 import QtCore, QtWidgets
    from syncbridge_maya import viewer_window

    cmds.scriptEditorInfo(historyFilename=os.path.join(OUT, "script_editor.txt"), writeHistory=True)
    cmds.file(new=True, force=True)
    # -- SETUP: build the scene here (cameras, meshes, layer_mapping.add_layer, ...) --------------------
    win = viewer_window.show()
    win.resize(1300, 1000)
    win.move(40, 40)
    win.setWindowFlags(win.windowFlags() | QtCore.Qt.WindowType.WindowStaysOnTopHint)   # over other windows
    win.show()
except Exception:
    log(traceback.format_exc())
    raise


def grab(name, whole=True):
    """The viewer's Maya view (name.png) and the whole window (name_window.png), as on screen."""
    view = omui2.M3dView.getM3dViewFromModelPanel(win.panel)
    view.refresh(force=True)
    QtWidgets.QApplication.processEvents()
    screen = QtWidgets.QApplication.primaryScreen()
    w = win._view_widget
    top_left = w.mapToGlobal(QtCore.QPoint(0, 0))
    screen.grabWindow(0, top_left.x(), top_left.y(), w.width(), w.height()).save(os.path.join(OUT, name + ".png"))
    if whole:
        geo = win.frameGeometry()
        screen.grabWindow(0, geo.x(), geo.y(), geo.width(), geo.height()).save(
            os.path.join(OUT, name + "_window.png"))


STEPS = []


def step(fn):
    STEPS.append(fn)
    return fn


# -- STEPS: one action each (a click, a frame change, a grab); log what is checked -------------------------
@step
def first():
    log("status", win.status.text())


STEPS.append(lambda: grab("1_first"))


def run(i=0):
    try:
        STEPS[i]()
    except Exception:
        log(traceback.format_exc())
        LOG.close()
        cmds.quit(force=True)
        return
    if i + 1 < len(STEPS):
        QtCore.QTimer.singleShot(STEP_MS, lambda: run(i + 1))
    else:
        log("done")
        LOG.close()
        cmds.quit(force=True)


QtCore.QTimer.singleShot(4000, run)      # after Maya's own start-up
