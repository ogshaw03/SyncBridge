"""The viewer's AE-like layer list (D-33) with offscreen Qt. Skipped without PySide6."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "maya_plugin", "scripts"))

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtWidgets
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

from syncbridge.core import layer_mapping as lm


@unittest.skipUnless(HAVE_QT, "needs PySide6 (requirements-monitor.txt)")
class LayerStackListTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        from syncbridge_maya.layer_stack_view import LayerStackList
        self.store = lm.empty_store()
        self.char = lm.new_maya_layer("CHAR", "S", "|S", [{"uuid": "c", "name": "|char"}], "SB-C", "|S|SB_CHAR_CAM|x")
        self.bg = lm.new_maya_layer("BG", "S", "|S", [{"uuid": "t", "name": "|town"}], "SB-B", "|S|SB_BG_CAM|x")
        self.fx = lm.new_maya_layer("FX")
        self.store["maya_layers"] += [self.char, self.bg, self.fx]
        self.list = LayerStackList()
        self.addCleanup(self.list.deleteLater)
        self.list.set_data(self.store)

    def test_motion_from_the_right_click_menu(self):
        # the viewer can transfer without the layer map (the user, 2026-10-25): only layers with a link
        lm.connect(self.store, {"comp_id": 1, "comp": "c", "layer_id": 5, "layer": "BG"}, self.bg["id"])
        self.list.set_data(self.store)
        got = []
        self.list.motion_requested.connect(got.append)
        tree = self.list.tree
        char_action = self.list.menu_for(tree.topLevelItem(0)).actions()[0]
        self.assertFalse(char_action.isEnabled())
        bg_action = self.list.menu_for(tree.topLevelItem(1)).actions()[0]
        self.assertTrue(bg_action.isEnabled())
        bg_action.trigger()
        self.assertEqual(got, [self.bg["id"]])

    def test_rows_top_first(self):
        from syncbridge_maya.layer_stack_view import CAMERA, NAME
        tree = self.list.tree
        self.assertEqual([tree.topLevelItem(i).text(NAME) for i in range(3)], ["CHAR", "BG", "FX"])
        self.assertEqual(tree.topLevelItem(1).text(CAMERA), "SB_BG_CAM")
        self.assertIn(u"描きません", tree.topLevelItem(2).toolTip(NAME))           # no camera, no objects

    def test_resolution_and_solo(self):
        # D-49: the AE size of each layer, and the solo button right of the eye
        from syncbridge_maya.layer_stack_view import RESOLUTION, SOLO
        lm.connect(self.store, {"comp_id": 1, "comp": "c", "layer_id": 5, "layer": "BG", "source_width": 3000,
                                "source_height": 1688, "source_kind": "still"}, self.bg["id"], mode="source")
        self.list.set_data(self.store)
        tree = self.list.tree
        self.assertEqual([tree.topLevelItem(i).text(RESOLUTION) for i in range(3)], [u"―", u"3000×1688（素材）", u"―"])
        got = []
        self.list.solo_requested.connect(got.append)
        bg_button = tree.itemWidget(tree.topLevelItem(1), SOLO)
        self.assertEqual(bg_button.text(), "")                 # a mark, not the word
        self.assertFalse(bg_button.icon().isNull())
        self.assertFalse(tree.headerItem().icon(SOLO).isNull())
        self.assertFalse(tree.itemWidget(tree.topLevelItem(2), SOLO).isEnabled())   # FX cannot be drawn
        bg_button.click()
        bg_button.click()
        self.assertEqual(got, [self.bg["id"], None])
        self.list.set_solo(self.bg["id"])                      # the viewer says which row is solo
        self.assertTrue(bg_button.isChecked())
        self.assertEqual(len(got), 2)                          # showing it does not ask again
        # D-54: the layout drawing's button, only with its row's solo on
        from syncbridge_maya.layer_stack_view import PLAN
        wanted = []
        self.list.plan_requested.connect(wanted.append)
        plans = [tree.itemWidget(tree.topLevelItem(i), PLAN) for i in range(3)]
        self.assertFalse(any(p.isEnabled() for p in plans))    # the viewer has not said it is possible
        self.list.set_plan(True, True)
        self.list.set_solo(self.bg["id"])
        self.assertEqual([p.isEnabled() for p in plans], [False, True, False])
        self.assertEqual([p.isChecked() for p in plans], [False, True, False])
        plans[1].click()
        self.assertEqual(wanted, [False])
        self.list.set_solo(None)
        self.assertFalse(any(p.isEnabled() or p.isChecked() for p in plans))
        self.assertEqual(wanted, [False])                      # showing it does not ask again
        self.list.set_solo(self.bg["id"])
        self.assertFalse(plans[1].isChecked())                 # the choice is kept
        self.assertTrue(plans[1].isEnabled())
        self.assertEqual(tree.topLevelItem(0).foreground(RESOLUTION).color().name(), "#7a7a7a")

    def test_reorder_emits_the_new_order(self):
        from syncbridge_maya.layer_stack_view import NUMBER, SOLO
        got = []
        self.list.order_changed.connect(got.append)
        tree = self.list.tree
        item = tree.takeTopLevelItem(1)                       # what a drag of BG to the top does
        tree.insertTopLevelItem(0, item)
        self.list._on_drop()
        self.assertEqual(got, [[self.bg["id"], self.char["id"], self.fx["id"]]])
        self.assertEqual(tree.topLevelItem(0).text(NUMBER), "1")
        self.assertIsNotNone(tree.itemWidget(tree.topLevelItem(0), SOLO))     # the moved row keeps its button

    def test_eye(self):
        got = []
        self.list.visible_changed.connect(lambda i, v: got.append((i, v)))
        self.list.tree.topLevelItem(0).setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        self.assertEqual(got, [(self.char["id"], False)])
        self.char["visible"] = False
        self.list.set_data(self.store)                         # refilling does not emit
        self.assertEqual(len(got), 1)
        self.assertEqual(self.list.tree.topLevelItem(0).checkState(0), QtCore.Qt.CheckState.Unchecked)


if __name__ == "__main__":
    unittest.main()
