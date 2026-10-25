"""maya_plugin/drag_to_maya_SyncBridge.py with a fake Maya (shelf calls are recorded)."""
import os
import runpy
import sys
import tempfile
import types
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DRAG_FILE = os.path.join(REPO, "maya_plugin", "drag_to_maya_SyncBridge.py")
FAKE_MODULES = ("maya", "maya.cmds", "maya.mel", "maya.utils", "maya.OpenMayaUI",
                "PySide2", "shiboken2", "PySide6", "shiboken6")


class FakeMaya:
    def __init__(self):
        self.buttons = {}           # name -> kwargs
        self.dialogs = []
        self.saved = 0
        self.count = 0

    def install(self):
        cmds = types.ModuleType("maya.cmds")
        cmds.tabLayout = lambda top, q=False, selectTab=False: "Custom"
        cmds.shelfLayout = lambda shelf, q=False, childArray=False: list(self.buttons)
        cmds.objectTypeUI = lambda name: "shelfButton"
        cmds.shelfButton = self.shelf_button
        cmds.deleteUI = lambda name: self.buttons.pop(name)
        cmds.confirmDialog = lambda **kw: self.dialogs.append(kw["message"]) or "OK"
        cmds.playbackOptions = lambda **kw: 1.0
        mel = types.ModuleType("maya.mel")
        mel.eval = self.mel_eval
        maya = types.ModuleType("maya")
        maya.cmds, maya.mel = cmds, mel
        maya.utils = types.ModuleType("maya.utils")
        maya.utils.executeDeferred = lambda fn: fn()
        maya.OpenMayaUI = types.ModuleType("maya.OpenMayaUI")
        qt = types.ModuleType("PySide2")
        qt.QtCore = types.SimpleNamespace(Qt=types.SimpleNamespace(Tool=0, WaitCursor=0))
        qt.QtWidgets = types.SimpleNamespace(QDialog=object)
        qt.QtGui = types.SimpleNamespace()
        shiboken = types.ModuleType("shiboken2")
        shiboken.wrapInstance = lambda ptr, cls: None
        sys.modules.update({"maya": maya, "maya.cmds": cmds, "maya.mel": mel, "maya.utils": maya.utils,
                            "maya.OpenMayaUI": maya.OpenMayaUI, "PySide2": qt, "shiboken2": shiboken})

    def shelf_button(self, name=None, q=False, docTag=False, **kw):
        if q:
            return self.buttons[name].get("docTag")
        self.count += 1
        button = "shelfButton%d" % self.count
        self.buttons[button] = dict(kw, docTag=docTag)
        return button

    def mel_eval(self, text):
        if text.startswith("saveAllShelves"):
            self.saved += 1
            return None
        return "ShelfLayout"


class DragInstallTest(unittest.TestCase):
    def setUp(self):
        self.saved_modules = {k: sys.modules[k] for k in list(sys.modules)
                              if k in FAKE_MODULES or k.startswith("syncbridge_maya")}
        for k in self.saved_modules:
            del sys.modules[k]
        self.saved_path = list(sys.path)
        self.maya = FakeMaya()
        self.maya.install()
        self.old_local = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()   # no installed copy: use the repo layout

    def tearDown(self):
        for k in [k for k in sys.modules if k in FAKE_MODULES or k.startswith("syncbridge_maya")]:
            del sys.modules[k]
        sys.modules.update(self.saved_modules)
        sys.path[:] = self.saved_path
        if self.old_local is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self.old_local

    def drop(self):
        ns = runpy.run_path(DRAG_FILE, run_name="__main__")   # like running the dropped file
        ns["onMayaDroppedPythonFile"]("drop")                  # Maya may also call this
        return ns

    def test_adds_one_button_and_replaces_on_reinstall(self):
        self.drop()
        self.assertEqual(len(self.maya.buttons), 1)
        self.assertEqual(len(self.maya.dialogs), 1, "installed twice in one drop")
        button = list(self.maya.buttons.values())[0]
        self.assertEqual(button["docTag"], "SyncBridge")
        self.assertTrue(button["image"].endswith("icons/syncbridge_shelf.png"))
        scripts = os.path.join(REPO, "maya_plugin", "scripts")
        self.assertIn(scripts, button["command"])
        self.assertIn("syncbridge_maya.ui.show()", button["command"])
        self.assertEqual(self.maya.saved, 1)
        self.drop()                                            # second drop: replaced, not added
        self.assertEqual(len(self.maya.buttons), 1)

    def test_button_command_runs(self):
        self.drop()
        command = list(self.maya.buttons.values())[0]["command"]
        compile(command, "<shelf button>", "exec")

    def test_installed_copy_is_preferred(self):
        ns = runpy.run_path(DRAG_FILE, run_name="drag")
        installed = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "SyncBridge", "maya")
        os.makedirs(os.path.join(installed, "scripts", "syncbridge_maya"))
        open(os.path.join(installed, "scripts", "syncbridge_maya", "ui.py"), "w").close()
        self.assertEqual(ns["find_maya_folder"](), os.path.normpath(installed))

    def test_missing_files_show_guidance(self):
        ns = runpy.run_path(DRAG_FILE, run_name="drag")
        ns["find_maya_folder"] = lambda: None
        ns["install"].__globals__["find_maya_folder"] = lambda: None
        self.assertFalse(ns["install"]())
        self.assertIn("Install.bat", self.maya.dialogs[-1])
        self.assertEqual(self.maya.buttons, {})


if __name__ == "__main__":
    unittest.main()
