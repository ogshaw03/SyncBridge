"""The layer map's node editor (D-28) with offscreen Qt: nodes, wires, drag to connect, Delete to
disconnect. Skipped without PySide6 (requirements-monitor.txt)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "maya_plugin", "scripts"))

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtTest, QtWidgets
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

from syncbridge.core import layer_mapping as lm

COMP = {"id": 12, "name": "c010", "width": 1920, "height": 1080, "frameRate": 24}
AE = {"comp": COMP, "layers": [
    {"id": 5, "index": 1, "name": "BG", "kind": "still", "width": 6000, "height": 4000},
    {"id": 6, "index": 2, "name": "CAM", "kind": "camera"},
    {"id": 7, "index": 3, "name": "CHAR", "kind": "sequence", "width": 1920, "height": 1080}]}


@unittest.skipUnless(HAVE_QT, "needs PySide6 (requirements-monitor.txt)")
class LayerMapViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        from syncbridge_maya.layer_map_view import LayerMapEditor
        self.store = lm.empty_store()
        self.layer = lm.new_maya_layer("BG", "cam", "|BG_CAM|BG_CAMShape")
        self.store["maya_layers"].append(self.layer)
        # D-40: only the AE layers put on the map are shown (BG and CHAR here, not CAM)
        lm.show_ae(self.store, [lm.ae_from_layers_info(COMP, AE["layers"][0]),
                                lm.ae_from_layers_info(COMP, AE["layers"][2])])
        self.editor = LayerMapEditor()
        self.addCleanup(self.editor.deleteLater)
        self.editor.resize(1000, 600)
        self.editor.set_data(AE, self.store)
        self.editor.show()
        self.app.processEvents()

    def nodes(self, kind):
        from syncbridge_maya.layer_map_view import Node
        return [n for n in self.editor.scene.items() if isinstance(n, Node) and n.kind == kind]

    def wires(self):
        return [i for i in self.editor.scene.items() if getattr(i, "mapping", None)]

    def test_layers_on_the_map_only_unless_asked(self):
        self.assertEqual(sorted(n.title for n in self.nodes("ae")), ["1  BG", "3  CHAR"])
        self.editor.all_check.setChecked(True)
        self.assertEqual([(n.title, n.dim) for n in sorted(self.nodes("ae"), key=lambda n: n.title)],
                         [("1  BG", False), ("2  CAM", True), ("3  CHAR", False)])

    def test_empty_map_says_what_to_do(self):
        self.editor.set_data(AE, lm.empty_store())
        self.assertEqual(self.nodes("ae"), [])
        texts = [i.toPlainText() for i in self.editor.scene.items() if isinstance(i, QtWidgets.QGraphicsTextItem)]
        self.assertTrue(any(u"AE の選択を追加" in t for t in texts))

    def test_take_off_the_map(self):
        got = []
        self.editor.hide_ae_requested.connect(got.append)
        bg = [n for n in self.nodes("ae") if n.title.endswith("BG")][0]
        bg.setSelected(True)
        self.assertTrue(self.editor.hide_ae_btn.isEnabled())
        self.editor._on_delete_key()                                     # the Delete key
        self.assertEqual(got, [bg.key])
        lm.connect(self.store, lm.ae_from_layers_info(COMP, AE["layers"][0]), self.layer["id"])
        self.editor.set_data(AE, self.store)
        bg = [n for n in self.nodes("ae") if n.title.endswith("BG")][0]
        bg.setSelected(True)
        self.assertFalse(self.editor.hide_ae_btn.isEnabled())           # linked: disconnect first

    def test_on_the_map_before_ae_is_read(self):
        from syncbridge_maya.layer_map_view import LayerMapEditor
        editor = LayerMapEditor()
        self.addCleanup(editor.deleteLater)
        editor.set_data(None, self.store)
        nodes = [n for n in editor.scene.items() if getattr(n, "kind", None) == "ae"]
        self.assertEqual(sorted(n.title for n in nodes), ["BG", "CHAR"])
        self.assertFalse(any(n.dim for n in nodes))

    def test_drag_from_the_port_connects(self):
        got = []
        self.editor.link_requested.connect(lambda ae, layer_id: got.append((ae, layer_id)))
        src = [n for n in self.nodes("ae") if n.title.endswith("BG")][0]
        view, vp = self.editor.view, self.editor.view.viewport()
        start = view.mapFromScene(src.port_pos())
        end = view.mapFromScene(self.nodes("maya")[0].mapToScene(QtCore.QPointF(100, 30)))
        QtTest.QTest.mousePress(vp, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier, start)
        for i in range(1, 6):
            p = start + (end - start) * i / 5
            QtTest.QTest.mouseMove(vp, QtCore.QPoint(int(p.x()), int(p.y())))
        QtTest.QTest.mouseRelease(vp, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier, end)
        self.assertEqual(len(got), 1)
        self.assertEqual(view.dragMode(), QtWidgets.QGraphicsView.DragMode.NoDrag)      # no rubber band
        self.assertEqual((got[0][0], got[0][1]), (lm.ae_from_layers_info(COMP, AE["layers"][0]), self.layer["id"]))

    def test_middle_drag_tracks_the_view(self):
        # like Maya's Node Editor (the user, 2026-10-25); the nodes start in the middle of the view
        view, vp = self.editor.view, self.editor.view.viewport()
        middle = QtCore.QPoint(vp.width() // 2, vp.height() // 2)
        nodes = self.editor.scene.itemsBoundingRect().center()
        self.assertLess((view.mapToScene(middle) - nodes).manhattanLength(), 2.0)
        before = view.mapToScene(middle)
        mid = QtCore.Qt.MouseButton.MiddleButton
        QtTest.QTest.mousePress(vp, mid, QtCore.Qt.KeyboardModifier.NoModifier, middle)
        for i in range(1, 6):
            QtTest.QTest.mouseMove(vp, middle + QtCore.QPoint(60 * i, 30 * i))
        QtTest.QTest.mouseRelease(vp, mid, QtCore.Qt.KeyboardModifier.NoModifier, middle + QtCore.QPoint(300, 150))
        moved = before - view.mapToScene(middle)
        scale = view.transform().m11()
        self.assertAlmostEqual(moved.x(), 300 / scale, delta=1.0)        # the scene follows the mouse
        self.assertAlmostEqual(moved.y(), 150 / scale, delta=1.0)
        self.assertEqual(view.dragMode(), QtWidgets.QGraphicsView.DragMode.NoDrag)
        self.assertLessEqual(view.sizeHint().width(), 600)              # the room must not make the window huge
        self.editor.set_data(AE, self.store)                             # a refresh does not jump back
        self.assertLess((before - view.mapToScene(middle) - moved).manhattanLength(), 1.0)

    def test_double_click_shows_the_layer(self):
        # D-31: a double click on a Maya layer node asks to show it in the view; it is then marked
        got = []
        self.editor.view_layer_requested.connect(got.append)
        node = self.nodes("maya")[0]
        pos = self.editor.view.mapFromScene(node.mapToScene(QtCore.QPointF(100, 30)))
        QtTest.QTest.mouseDClick(self.editor.view.viewport(), QtCore.Qt.MouseButton.LeftButton,
                                 QtCore.Qt.KeyboardModifier.NoModifier, pos)
        self.assertEqual(got, [self.layer["id"]])
        self.editor.viewing = self.layer["id"]
        self.editor.rebuild()
        self.assertIn(u"表示中", self.nodes("maya")[0].title)

    def test_viewer_button(self):
        got = []
        self.editor.viewer_requested.connect(lambda: got.append(True))
        self.editor.viewer_btn.click()
        self.assertEqual(got, [True])

    def test_wires_and_delete(self):
        link = lm.connect(self.store, lm.ae_from_layers_info(COMP, AE["layers"][0]), self.layer["id"])
        lm.connect(self.store, {"comp_id": 99, "comp": "c009", "layer_id": 1, "layer": "OLD"}, self.layer["id"],
                   method="film_offset")
        self.editor.set_data(None, self.store)          # None: keep the AE layers read before
        self.assertEqual(len(self.wires()), 2)
        missing = [n for n in self.nodes("ae") if n.dim]
        self.assertEqual([n.title for n in missing], ["OLD"])       # not in the comp read from AE
        self.assertIn(u"基準なし", [w for w in self.wires() if w.mapping is link][0].label)
        gone = []
        self.editor.unlink_requested.connect(gone.append)
        [w for w in self.wires() if w.mapping is link][0].setSelected(True)
        self.assertEqual(self.editor.inspector.currentIndex(), 3)
        self.editor.view.setFocus()
        QtTest.QTest.keyClick(self.editor.view, QtCore.Qt.Key.Key_Delete)
        self.assertEqual(gone, [link["id"]])


if __name__ == "__main__":
    unittest.main()
