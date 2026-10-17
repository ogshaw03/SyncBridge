"""Maya side of the comp guide (D-16) with a fake maya package. The plug-in needs Maya's
API and is only parsed here; drawing is checked in Maya (H-MY-19 to H-MY-22)."""
import ast
import os
import sys
import types
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAYA_SCRIPTS = os.path.join(REPO, "maya_plugin", "scripts")
PLUGIN = os.path.join(REPO, "maya_plugin", "plug-ins", "syncbridge_guide.py")


def _maya_modules():
    return [k for k in sys.modules if k == "maya" or k.startswith(("maya.", "syncbridge_maya"))]


class FakeCmds(types.ModuleType):
    """Just enough of maya.cmds for comp_guide.show(): one camera 'shotCam' in modelPanel4."""

    def __init__(self):
        super().__init__("maya.cmds")
        self.log = []
        self.loaded = False
        self.nodes = {}            # long name -> type
        self.attrs = {"defaultResolution.width": 2112, "defaultResolution.height": 1188,
                      "defaultResolution.deviceAspectRatio": 2112 / 1188.0, "defaultResolution.pixelAspect": 1.0}
        cam = {"orthographic": False, "orthographicWidth": 30.0, "focalLength": 35.0,
               "horizontalFilmAperture": 1.417, "verticalFilmAperture": 0.945, "horizontalFilmOffset": 0.0,
               "verticalFilmOffset": 0.0, "filmFit": 1, "lensSqueezeRatio": 1.0, "cameraScale": 1.0,
               "preScale": 1.0, "postScale": 1.0, "filmTranslateH": 0.0, "filmTranslateV": 0.0}
        for k, v in cam.items():
            self.attrs["|shotCam|shotCamShape.%s" % k] = v
        self.undo = []
        self.connections = {}      # destination plug -> source plug

    def pluginInfo(self, name, q=False, loaded=False, dependNode=False):
        if dependNode:
            return ["syncBridgeCompGuide"] if self.loaded and not self.broken_plugin else None
        return self.loaded

    broken_plugin = False

    def objExists(self, node):
        return node in self.nodes

    def loadPlugin(self, path, quiet=False):
        self.log.append(("loadPlugin", os.path.basename(path)))
        self.loaded = True

    def playblast(self, activeEditor=False):
        return "MayaWindow|formLayout|modelPanel4"

    def getPanel(self, withFocus=False, typeOf=None, visiblePanels=False):
        if typeOf:
            return "modelPanel" if typeOf.startswith("modelPanel") else "scriptedPanel"
        if withFocus:
            return "scriptEditorPanel1"
        return ["modelPanel4"]

    def modelEditor(self, editor, q=False, camera=False):
        assert editor == "modelPanel4", editor
        return "shotCamShape"

    def nodeType(self, node):
        return "camera" if node.endswith("Shape") else "transform"

    def listRelatives(self, node, parent=False, shapes=False, type=None, fullPath=False):
        if parent:
            if node in ("shotCamShape", "|shotCam|shotCamShape"):
                return ["|shotCam"]
            return [node.rsplit("|", 1)[0]] if "|" in node.strip("|") else None
        if shapes:
            return ["|shotCam|shotCamShape"] if node == "|shotCam" else []
        return []

    def ls(self, node=None, long=False, type=None):
        if type is not None:
            return [n for n, t in self.nodes.items() if t == type]
        return ["|" + node.strip("|")] if node else []

    def getAttr(self, plug):
        return self.attrs[plug]

    def setAttr(self, plug, *value, **kw):
        self.log.append(("setAttr", plug) + value + tuple(sorted(kw.items())))

    def createNode(self, node_type, name, parent=None, skipSelect=False):
        long_name = "%s|%s" % (parent or "", name)
        self.nodes[long_name] = node_type
        self.log.append(("createNode", node_type, long_name))
        return long_name

    def delete(self, nodes):
        nodes = [nodes] if isinstance(nodes, str) else list(nodes)
        self.log.append(("delete", nodes))
        for n in nodes:
            for k in [k for k in self.nodes if k == n or k.startswith(n + "|")]:
                del self.nodes[k]
                for dst in [d for d in self.connections if d.split(".")[0] == k]:
                    del self.connections[dst]

    def connectAttr(self, src, dst):
        self.log.append(("connectAttr", src, dst))
        self.connections[dst] = src

    def listConnections(self, plug, source=True, destination=True, shapes=False):
        src = self.connections.get(plug)
        return [src.split(".")[0]] if src else None

    def attributeQuery(self, attr, node=None, exists=False):
        return True

    option_vars = None

    def optionVar(self, exists=None, q=None, stringValue=None):
        if self.option_vars is None:
            self.option_vars = {}
        if exists is not None:
            return exists in self.option_vars
        if q is not None:
            return self.option_vars[q]
        name, value = stringValue
        self.option_vars[name] = value

    undo_state = True

    def undoInfo(self, q=False, state=False, stateWithoutFlush=None, **kw):
        if q and state:
            return self.undo_state
        if stateWithoutFlush is not None:
            self.undo.append("on" if stateWithoutFlush else "off")
            self.undo_state = stateWithoutFlush
            return None
        raise AssertionError("unexpected undoInfo %r" % kw)   # no undo chunks: not recorded for undo


class MayaCompGuideTest(unittest.TestCase):
    def setUp(self):
        self.saved = {k: sys.modules.pop(k) for k in _maya_modules()}
        maya = types.ModuleType("maya")
        self.cmds = FakeCmds()
        api = types.ModuleType("maya.api")
        om = types.ModuleType("maya.api.OpenMaya")
        self.do_not_write = []
        test = self

        class MSelectionList:
            def add(self, node):
                self.node = node

            def getDependNode(self, i):
                return self.node

        class MFnDependencyNode:
            def __init__(self, node):
                self.node = node

            def setDoNotWrite(self, flag):
                test.do_not_write.append((self.node, flag))

        om.MSelectionList, om.MFnDependencyNode = MSelectionList, MFnDependencyNode
        api.OpenMaya = om
        utils = types.ModuleType("maya.utils")
        utils.executeDeferred = lambda fn: fn()
        maya.cmds, maya.api, maya.utils = self.cmds, api, utils
        sys.modules.update({"maya": maya, "maya.cmds": self.cmds, "maya.api": api,
                            "maya.api.OpenMaya": om, "maya.utils": utils})
        sys.path.insert(0, MAYA_SCRIPTS)
        from syncbridge_maya import comp_guide
        self.guide = comp_guide

    def tearDown(self):
        sys.path.remove(MAYA_SCRIPTS)
        for k in _maya_modules():
            del sys.modules[k]
        sys.modules.update(self.saved)

    def test_plugin_path_is_next_to_scripts(self):
        self.assertEqual(os.path.normcase(self.guide.plugin_path()), os.path.normcase(PLUGIN))

    def test_active_camera_from_the_active_editor(self):
        self.assertEqual(self.guide.active_camera(), "|shotCam")

    def test_show_creates_one_guide_linked_to_the_camera(self):
        result = self.guide.show({"name": "main", "width": 1920, "height": 1080})
        self.assertEqual(result, {"status": "applied", "camera": "shotCam", "render": [2112, 1188],
                                  "comp": [1920, 1080], "warnings": []})
        self.assertIn(("loadPlugin", "syncbridge_guide.py"), self.cmds.log)
        created = [e for e in self.cmds.log if e[0] == "createNode"]
        # In the world, not under the camera: Maya 2023 never drew it there (D-16).
        self.assertEqual(created, [("createNode", "transform", "|syncBridgeCompGuide"),
                                   ("createNode", "syncBridgeCompGuide", "|syncBridgeCompGuide|syncBridgeCompGuideShape")])
        self.assertIn(("connectAttr", "|shotCam|shotCamShape.worldMatrix[0]", "|syncBridgeCompGuide|syncBridgeCompGuideShape.cameraMatrix"), self.cmds.log)
        self.assertEqual(self.guide.guide_camera("|syncBridgeCompGuide|syncBridgeCompGuideShape"), "|shotCam")
        self.assertIn(("setAttr", "|syncBridgeCompGuide.hiddenInOutliner", True), self.cmds.log)
        self.assertIn(("setAttr", "|syncBridgeCompGuide|syncBridgeCompGuideShape.compWidth", 1920),
                      self.cmds.log)
        self.assertEqual([flag for _, flag in self.do_not_write], [True, True])   # never saved (H-MY-22)
        # Not recorded for undo (an undo after a save crashed Maya 2024 otherwise), state restored.
        self.assertEqual(self.cmds.undo, ["off", "on"])

    def test_show_again_replaces_the_old_guide(self):
        self.guide.show({"name": "a", "width": 1920, "height": 1080})
        self.guide.show({"name": "b", "width": 1280, "height": 720})
        self.assertEqual(len(self.guide.existing()), 1)
        self.assertIn(("delete", ["|syncBridgeCompGuide"]), self.cmds.log)

    def test_warning_when_the_comp_is_larger(self):
        result = self.guide.show({"name": "big", "width": 4096, "height": 2160})
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn(u"はみ出します", result["warnings"][0])

    def test_plugin_that_fails_to_load_creates_nothing(self):
        # Maya 2024: loadPlugin did not raise when the plug-in's code failed, and createNode then
        # made an "unknown" node; the panel showed a confusing setAttr error.
        self.cmds.broken_plugin = True
        with self.assertRaises(RuntimeError) as ctx:
            self.guide.show({"name": "main", "width": 1920, "height": 1080})
        self.assertIn(u"プラグインを読み込めませんでした", str(ctx.exception))
        self.assertEqual([e for e in self.cmds.log if e[0] == "createNode"], [])

    def test_failure_after_create_leaves_nothing_behind(self):
        def failing_set(plug, *value, **kw):
            raise RuntimeError("setAttr: boom")
        self.cmds.setAttr = failing_set
        with self.assertRaises(RuntimeError):
            self.guide.show({"name": "main", "width": 1920, "height": 1080})
        self.assertEqual(self.cmds.nodes, {})
        self.assertEqual(self.cmds.undo, ["off", "on"])

    def test_undo_turned_off_by_the_user_stays_off(self):
        self.cmds.undo_state = False
        self.guide.show({"name": "main", "width": 1920, "height": 1080})
        self.assertFalse(self.cmds.undo_state)

    def test_save_takes_the_guide_out_and_puts_it_back(self):
        # Maya 2024 writes `requires "syncbridge_guide.py"` while a guide exists (H-MY-22).
        self.cmds.attrs.update({"|syncBridgeCompGuide|syncBridgeCompGuideShape.compWidth": 1920,
                                "|syncBridgeCompGuide|syncBridgeCompGuideShape.compHeight": 1080,
                                "|syncBridgeCompGuide|syncBridgeCompGuideShape.compName": "main",
                                "|syncBridgeCompGuide|syncBridgeCompGuideShape.lineWidth": 3.0})
        self.cmds.nodes["|shotCam"] = "transform"
        self.guide.show({"name": "main", "width": 1920, "height": 1080})
        stash = self.guide.take_out_for_save()
        self.assertEqual(stash, [{"camera": "|shotCam", "width": 1920, "height": 1080, "name": "main",
                                  "line_width": 3.0}])
        self.assertEqual(self.guide.existing(), [])
        self.guide.put_back_after_save(stash)
        self.assertEqual(self.guide.existing(), ["|syncBridgeCompGuide|syncBridgeCompGuideShape"])
        self.assertIn(("setAttr", "|syncBridgeCompGuide|syncBridgeCompGuideShape.lineWidth", 3.0),
                      self.cmds.log)
        self.assertTrue(self.cmds.undo_state)

    def test_size_typed_in_the_panel(self):
        # The AE project may have no comp of the final size: the Maya panel takes width / height.
        self.assertEqual(self.guide.last_size(), (1920, 1080))
        result = self.guide.show_size(2048, 858)
        self.assertEqual((result["status"], result["comp"]), ("applied", [2048, 858]))
        self.assertIn(("setAttr", "|syncBridgeCompGuide|syncBridgeCompGuideShape.compName", "", ("type", "string")),
                      self.cmds.log)                           # no "AE" in the label
        self.assertEqual(self.guide.last_size(), (2048, 858))   # remembered for next time
        self.cmds.option_vars[self.guide.SIZE_OPTION_VAR] = "garbage"
        self.assertEqual(self.guide.last_size(), (1920, 1080))

    def test_presets(self):
        for name, width, height in self.guide.PRESETS:
            self.assertTrue(name and width > 0 and height > 0)
        self.assertIn(("HD", 1920, 1080), self.guide.PRESETS)

    def test_bad_comp_changes_nothing(self):
        with self.assertRaises(ValueError):
            self.guide.show({"width": -1, "height": 10})
        self.assertEqual([e for e in self.cmds.log if e[0] == "createNode"], [])

    def test_clear(self):
        self.assertEqual(self.guide.clear(), 0)
        self.guide.show({"name": "a", "width": 1920, "height": 1080})
        self.assertEqual(self.guide.clear(), 1)
        self.assertEqual(self.guide.existing(), [])

    def test_service_handler_reports_to_the_panel(self):
        sys.modules["maya"].mel = types.ModuleType("maya.mel")
        self.cmds.warning = lambda *a: None
        self.cmds.about = lambda **kw: "2024"
        from syncbridge_maya import service
        events = []
        service.add_listener(lambda e, p: events.append((e, p)))
        reply = service._handle_guide({"data": {"guide": {"name": "main", "width": 1920, "height": 1080}}})
        self.assertEqual(reply["status"], "applied")
        self.assertEqual(events[-1][0], "guide")
        self.assertEqual(events[-1][1]["name"], "main")
        # The label in the view says the size came from AE.
        self.assertIn(("setAttr", "|syncBridgeCompGuide|syncBridgeCompGuideShape.compName", "AE main",
                       ("type", "string")), self.cmds.log)


class PluginSourceTest(unittest.TestCase):
    def test_plugin_parses_and_registers(self):
        with open(PLUGIN, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        for name in ("maya_useNewAPI", "initializePlugin", "uninitializePlugin", "CompGuideNode",
                     "CompGuideDrawOverride"):
            self.assertIn(name, names)


if __name__ == "__main__":
    unittest.main()
