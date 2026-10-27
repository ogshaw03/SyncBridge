"""The viewer's layer list (D-33): the Maya layers like AE's timeline layers, top = front.

Qt only (PySide2 / PySide6), Maya is not imported: the viewer window (viewer_window.py) connects it.

    lst = LayerStackList()
    lst.set_data(store)                         # the scene's layer map (core.layer_mapping)
    lst.order_changed.connect(...)              # [layer ids], top first, after a row is dragged
    lst.visible_changed.connect(...)            # (layer id, bool), the eye
    lst.motion_requested.connect(...)           # layer id, from the row's right-click menu
"""
from __future__ import annotations

from typing import List

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

from syncbridge.core import layer_mapping as core_lm

Qt = QtCore.Qt
ID_ROLE = Qt.ItemDataRole.UserRole
COLUMNS = (u"表示", u"#", u"レイヤー名", u"カメラ", u"AE のレイヤー", u"オブジェクト")
LABEL_COLORS = ("#b85c5c", "#c8a24a", "#5ca05c", "#4f86c6", "#9b6bc0", "#4fb0b0", "#c07a3c", "#8a8a8a")


class _Tree(QtWidgets.QTreeWidget):
    """Rows can be dragged to reorder, never dropped into each other."""
    dropped = QtCore.Signal()

    def dropEvent(self, event):
        super().dropEvent(event)
        self.dropped.emit()


class LayerStackList(QtWidgets.QWidget):
    order_changed = QtCore.Signal(list)        # layer ids, top (front) first
    visible_changed = QtCore.Signal(str, bool)
    motion_requested = QtCore.Signal(str)      # layer id: transfer the AE motion of its links (D-30)
    editing_requested = QtCore.Signal(str)     # layer id: edit it in the viewer (D-44), a row clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tree = _Tree()
        self.tree.setColumnCount(len(COLUMNS))
        self.tree.setHeaderLabels(list(COLUMNS))
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        header = self.tree.header()
        for col, width in ((0, 44), (1, 30), (2, 170), (3, 190), (4, 170)):
            header.resizeSection(col, width)
        header.setStretchLastSection(True)
        self.tree.dropped.connect(self._on_drop)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.itemClicked.connect(self._on_clicked)
        self.hint = QtWidgets.QLabel(u"上の行ほど手前に重なります。行をドラッグして並べ替え、左のチェックで表示・非表示。"
                                     u"行をクリックすると、そのレイヤーを編集中にします（ビューでの選択・移動がそのレイヤーの"
                                     u"見え方どおりになります）。カメラか表示するオブジェクトのないレイヤーは描きません。")
        self.hint.setStyleSheet("color: #9a9a9a;")
        self.hint.setWordWrap(True)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.tree, 1)
        lay.addWidget(self.hint)
        self._filling = False
        self.editing = None

    def set_editing(self, layer_id) -> None:
        """Mark the layer edited in the viewer (bold, "（編集中）"; a symbol was a box in mayapy's font)."""
        self.editing = layer_id
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            mine = item.data(0, ID_ROLE) == layer_id
            font = item.font(2)
            font.setBold(mine)
            item.setFont(2, font)
            name = item.data(2, ID_ROLE) or item.text(2)
            item.setData(2, ID_ROLE, name)
            item.setText(2, (name + u"（編集中）") if mine else name)

    def _on_clicked(self, item, column):
        if column != 0:                                          # the eye toggles, it does not choose
            self.editing_requested.emit(item.data(0, ID_ROLE))

    def set_data(self, store: dict) -> None:
        self._filling = True
        try:
            current = self.selected_id()
            self.tree.clear()
            drawn = set(s["id"] for s in core_lm.stack(dict(store, maya_layers=[
                dict(layer, visible=True) for layer in store["maya_layers"]])))
            for i, layer in enumerate(store["maya_layers"]):
                links = core_lm.links_of(store, layer["id"])
                cam = core_lm.driven_camera(layer)
                item = QtWidgets.QTreeWidgetItem([
                    "", str(i + 1), layer["name"],
                    _transform_name(cam["camera"]) if cam["camera"] else u"（カメラなし）",
                    u", ".join(m["ae"].get("layer") or "?" for m in links) or u"―",
                    str(len(layer.get("objects") or []))])
                item.setData(0, ID_ROLE, layer["id"])
                item.setFlags((item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled)
                              & ~Qt.ItemFlag.ItemIsDropEnabled)
                item.setCheckState(0, Qt.CheckState.Checked if layer.get("visible", True) else Qt.CheckState.Unchecked)
                item.setIcon(2, _swatch(LABEL_COLORS[i % len(LABEL_COLORS)]))
                if layer["id"] not in drawn:
                    for col in range(1, len(COLUMNS)):
                        item.setForeground(col, QtGui.QBrush(QtGui.QColor("#7a7a7a")))
                    item.setToolTip(2, u"カメラか表示するオブジェクトがないので描きません")
                self.tree.addTopLevelItem(item)
                if layer["id"] == current:
                    item.setSelected(True)
            self.set_editing(self.editing)
        finally:
            self._filling = False

    def order(self) -> List[str]:
        return [self.tree.topLevelItem(i).data(0, ID_ROLE) for i in range(self.tree.topLevelItemCount())]

    def selected_id(self):
        items = self.tree.selectedItems()
        return items[0].data(0, ID_ROLE) if items else None

    def _on_drop(self):
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setText(1, str(i + 1))
        self.order_changed.emit(self.order())

    def menu_for(self, item) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu(self)
        layer_id = item.data(0, ID_ROLE)
        action = menu.addAction(u"このレイヤーのアニメーションを転送…")
        action.setEnabled(item.text(4) != u"―")                  # no AE layer linked
        action.triggered.connect(lambda: self.motion_requested.emit(layer_id))
        return menu

    def _menu(self, pos):
        item = self.tree.itemAt(pos)
        if item is not None:
            item.setSelected(True)
            menu = self.menu_for(item)
            run = getattr(menu, "exec", None) or menu.exec_          # PySide6 / PySide2
            run(self.tree.viewport().mapToGlobal(pos))

    def _on_item_changed(self, item, column):
        if not self._filling and column == 0:
            self.visible_changed.emit(item.data(0, ID_ROLE), item.checkState(0) == Qt.CheckState.Checked)


def _transform_name(path: str) -> str:
    """The camera's transform (what the Outliner shows) from the shape's full path."""
    parts = path.split("|")
    return parts[-2] if len(parts) > 1 and parts[-2] else parts[-1]


def _swatch(color: str) -> QtGui.QIcon:
    pix = QtGui.QPixmap(10, 10)
    pix.fill(QtGui.QColor(color))
    return QtGui.QIcon(pix)
