"""SyncBridge viewer clicks: why a click does not select or change the editing layer. Run it in Maya's
Script Editor (Python) with the viewer open, then click in the viewer a few times:

    exec(open(r"<repository>/tools/viewer_click_probe.py", encoding="utf-8").read())

Writes the state and, for each of the next CLICKS clicks, where the press went, the selection and the
editing layer afterwards and what the viewer's pick finds, to <repository>/probe_results/viewer_click_probe.txt
(not in Git), then removes itself. Changes nothing in the scene.
"""
import __main__
import datetime
import os
import sys
import traceback

from maya import cmds

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

CLICKS = 6
KEY = "_syncbridge_click_probe"


def _out_path():
    import syncbridge_maya
    root = os.path.dirname(os.path.abspath(syncbridge_maya.__file__))
    for _ in range(3):
        root = os.path.dirname(root)
    if not os.path.isfile(os.path.join(root, "CLAUDE.md")):
        root = os.path.expanduser("~")
    folder = os.path.join(root, "probe_results")
    if not os.path.isdir(folder):
        os.makedirs(folder)
    return os.path.join(folder, "viewer_click_probe.txt")


class _Probe(QtCore.QObject):
    def __init__(self, path):
        super(_Probe, self).__init__()
        self.path = path
        self.left = CLICKS
        with open(path, "w", encoding="utf-8") as f:
            f.write("SyncBridge viewer click probe %s\n" % datetime.datetime.now().isoformat(" ", "seconds"))
        self.say("maya", cmds.about(version=True), "python", sys.version.split()[0])
        self.attempt("state", self.state)

    def say(self, *args):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(" ".join(str(a) for a in args) + "\n")

    def attempt(self, name, fn):
        try:
            fn()
        except Exception:
            self.say("!!", name, "failed:\n" + traceback.format_exc())

    @staticmethod
    def viewers():
        found = []
        for w in QtWidgets.QApplication.topLevelWidgets():
            try:
                if w.objectName() == "SyncBridgeViewer":
                    found.append(w)
            except RuntimeError:
                pass
        return found

    def viewer(self):
        from syncbridge_maya import viewer_window
        return viewer_window._window

    def state(self):
        import syncbridge_maya
        from syncbridge_maya import layer_mapping, layer_stack
        win = self.viewer()
        self.say("code", syncbridge_maya.__file__)
        self.say("viewer windows", len(self.viewers()), "module's window", win)
        self.say("tool", cmds.currentCtx(), "objectMode", cmds.selectMode(q=True, object=True), "frame", cmds.currentTime(q=True))
        self.say("selection", cmds.ls(selection=True, long=True))
        self.say("plug-ins", [(p, cmds.pluginInfo(p, q=True, path=True)) for p in cmds.pluginInfo(q=True, listPlugins=True) or []
                              if "syncbridge" in p.lower()])
        self.say("solo", layer_stack.solo(), "stack editing", layer_stack.editing())
        store = layer_mapping.store()
        for layer in store["maya_layers"]:
            nodes = [layer_mapping.node_by_uuid(o.get("uuid")) for o in layer.get("objects") or []]
            self.say("layer", layer["id"], layer["name"], "visible", layer.get("visible", True), "camera", layer.get("camera"),
                     "layer_camera", layer.get("layer_camera"), "objects", nodes)
        self.say("links", [(m.get("name"), m.get("mode"), m.get("method"), m.get("enabled")) for m in store.get("mappings") or []])
        if win is None:
            self.say("no viewer window")
            return
        self.say("editing", win._editing, "| label", win.camera_label.text(), "| status", win.status.text())
        self.say("panel", win.panel, "camera", cmds.modelEditor(win.panel, q=True, camera=True), "override",
                 cmds.modelEditor(win.panel, q=True, rendererOverrideName=True))
        w = win._view_widget
        self.say("view widget", w)
        if w is not None:
            self.say("view size", w.width(), w.height(), "visible", w.isVisible(), "enabled", w.isEnabled())
            centre = w.mapToGlobal(QtCore.QPoint(w.width() // 2, w.height() // 2))
            top = QtWidgets.QApplication.widgetAt(centre)
            self.say("widget at the view's centre", top, "is the view", top is w or (top is not None and w.isAncestorOf(top)))

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QtCore.QEvent.Type.MouseButtonPress and isinstance(obj, QtWidgets.QWidget):
            self.attempt("press", lambda: self.pressed(obj, event))
        elif kind == QtCore.QEvent.Type.MouseButtonRelease and isinstance(obj, QtWidgets.QWidget):
            pos = QtGui.QCursor.pos()
            QtCore.QTimer.singleShot(400, lambda: self.attempt("after", lambda: self.after(pos)))
        return False

    def pressed(self, obj, event):
        win = self.viewer()
        w = win._view_widget if win else None
        self.say("--- press on", type(obj).__name__, repr(obj.objectName()), "button", event.button(), "mods", event.modifiers(),
                 "| the view:", obj is w, "| in the view:", w is not None and (obj is w or w.isAncestorOf(obj)),
                 "| viewer's press seen:", getattr(win, "_press", None) is not None)
        self.say("    before: selection", cmds.ls(selection=True), "editing", getattr(win, "_editing", None), "tool", cmds.currentCtx())

    def after(self, pos):
        from syncbridge_maya import layer_mapping, viewer_pick
        win = self.viewer()
        self.say("    after: selection", cmds.ls(selection=True), "| editing", getattr(win, "_editing", None), "| label",
                 win.camera_label.text() if win else None, "| status", win.status.text() if win else None)
        w = win._view_widget if win else None
        if w is not None:
            p = w.mapFromGlobal(pos)
            if w.rect().contains(p):
                self.say("    pick at", p.x(), p.y(), "->", viewer_pick.pick(layer_mapping.store(), p.x(), p.y(), float(w.width()), float(w.height())))
                self.say("    on_selection", viewer_pick.on_selection(p.x(), p.y(), float(w.width()), float(w.height())))
            else:
                self.say("    outside the view", p.x(), p.y())
        self.left -= 1
        if self.left <= 0:
            remove()


def remove():
    probe = getattr(__main__, KEY, None)
    if probe is not None:
        QtWidgets.QApplication.instance().removeEventFilter(probe)
        probe.say("probe removed")
        setattr(__main__, KEY, None)


remove()
_probe = _Probe(_out_path())
setattr(__main__, KEY, _probe)
QtWidgets.QApplication.instance().installEventFilter(_probe)
print(u"SyncBridge: ビューアーで %d 回クリックしてください。記録: %s" % (CLICKS, _probe.path))
