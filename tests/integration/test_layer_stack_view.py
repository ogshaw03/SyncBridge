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

    def test_rows_top_first(self):
        tree = self.list.tree
        self.assertEqual([tree.topLevelItem(i).text(2) for i in range(3)], ["CHAR", "BG", "FX"])
        self.assertEqual(tree.topLevelItem(1).text(3), "SB_BG_CAM")
        self.assertIn(u"描きません", tree.topLevelItem(2).toolTip(2))           # no camera, no objects

    def test_reorder_emits_the_new_order(self):
        got = []
        self.list.order_changed.connect(got.append)
        tree = self.list.tree
        item = tree.takeTopLevelItem(1)                       # what a drag of BG to the top does
        tree.insertTopLevelItem(0, item)
        self.list._on_drop()
        self.assertEqual(got, [[self.bg["id"], self.char["id"], self.fx["id"]]])
        self.assertEqual(tree.topLevelItem(0).text(1), "1")

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
