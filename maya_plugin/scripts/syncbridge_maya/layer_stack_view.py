"""The viewer's layer list (D-33): the Maya layers like AE's timeline layers, top = front.

Qt only (PySide2 / PySide6), Maya is not imported: the viewer window (viewer_window.py) connects it.

    lst = LayerStackList()
    lst.set_data(store)                         # the scene's layer map (core.layer_mapping)
    lst.order_changed.connect(...)              # [layer ids], top first, after a row is dragged
    lst.visible_changed.connect(...)            # (layer id, bool), the eye
    lst.motion_requested.connect(...)           # layer id, from the row's right-click menu
    lst.solo_requested.connect(...)             # layer id, or None: the row's solo mark (D-49)
    lst.set_solo(layer_id)                      # show which row is solo (None: none)
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
COLUMNS = (u"表示", u"", u"", u"#", u"レイヤー名", u"AE の解像度", u"カメラ", u"AE のレイヤー", u"オブジェクト")   # solo, plan: marks
EYE, SOLO, PLAN, NUMBER, NAME, RESOLUTION, CAMERA, AE_LAYER, OBJECTS = range(len(COLUMNS))
MARK_HEIGHT = 18                                 # an icon button would make the rows taller
PLAN_TIP = (u"素材の上に、最初のキーと最後のキーのコンプの枠を出します（水色が最初、ピンクが最後）。回転とスケールも枠に出て、"
            u"数値は左下に出します。左の丸のボタン（単独）がオンのときだけ押せます")
SOLO_TIP = (u"このレイヤーの素材の全体を、AE のパン・ズームなしで、素材の解像度の枠の中に表示します"
            u"（素材カメラのモードの接続）。もう一度押すと元に戻ります")
LABEL_COLORS = ("#b85c5c", "#c8a24a", "#5ca05c", "#4f86c6", "#9b6bc0", "#4fb0b0", "#c07a3c", "#8a8a8a")


def _solo_pixmap(filled: bool, color: str) -> QtGui.QPixmap:
    """The solo mark, like AE's: a ring, filled when on. Drawn, not a character: a font may not have it."""
    scale = 2
    pixmap = QtGui.QPixmap(16 * scale, 16 * scale)
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.setPen(QtGui.QPen(QtGui.QColor(color), 1.5))
    painter.setBrush(QtGui.QColor(color) if filled else Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QtCore.QPointF(8.0, 8.0), 4.2, 4.2)
    painter.end()
    return pixmap


def _solo_icon() -> QtGui.QIcon:
    icon = QtGui.QIcon()
    icon.addPixmap(_solo_pixmap(False, "#c8c8c8"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
    icon.addPixmap(_solo_pixmap(True, "#ffffff"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.On)
    icon.addPixmap(_solo_pixmap(False, "#5e5e5e"), QtGui.QIcon.Mode.Disabled, QtGui.QIcon.State.Off)
    return icon


def _plan_pixmap(filled: bool, color: str) -> QtGui.QPixmap:
    """The layout drawing's mark (D-54): one picture inside the corners of a frame."""
    scale = 2
    pixmap = QtGui.QPixmap(16 * scale, 16 * scale)
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    pen = QtGui.QPen(QtGui.QColor(color), 1.3)
    painter.setPen(pen)
    for x, dx in ((1.5, 3.5), (14.5, -3.5)):
        for y, dy in ((1.5, 3.5), (14.5, -3.5)):
            painter.drawLine(QtCore.QPointF(x, y), QtCore.QPointF(x + dx, y))
            painter.drawLine(QtCore.QPointF(x, y), QtCore.QPointF(x, y + dy))
    if filled:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(color))
    painter.drawRect(QtCore.QRectF(4.8, 5.6, 6.4, 4.8))
    painter.end()
    return pixmap


def _plan_icon() -> QtGui.QIcon:
    icon = QtGui.QIcon()
    icon.addPixmap(_plan_pixmap(False, "#c8c8c8"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
    icon.addPixmap(_plan_pixmap(True, "#ffffff"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.On)
    icon.addPixmap(_plan_pixmap(False, "#5e5e5e"), QtGui.QIcon.Mode.Disabled, QtGui.QIcon.State.Off)
    return icon


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
    solo_requested = QtCore.Signal(object)     # layer id, or None to show every layer again (D-49)
    plan_requested = QtCore.Signal(bool)       # the layout drawing's frames on / off (D-54)

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
        self.tree.headerItem().setIcon(SOLO, QtGui.QIcon(_solo_pixmap(True, "#c8c8c8")))
        self.tree.headerItem().setToolTip(SOLO, SOLO_TIP)
        self.tree.headerItem().setIcon(PLAN, QtGui.QIcon(_plan_pixmap(True, "#c8c8c8")))
        self.tree.headerItem().setToolTip(PLAN, PLAN_TIP)
        header = self.tree.header()
        for col, width in ((EYE, 44), (SOLO, 34), (PLAN, 34), (NUMBER, 30), (NAME, 170), (RESOLUTION, 150), (CAMERA, 170),
                           (AE_LAYER, 150)):
            header.resizeSection(col, width)
        header.setStretchLastSection(True)
        self.tree.dropped.connect(self._on_drop)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.itemClicked.connect(self._on_clicked)
        self.hint = QtWidgets.QLabel(u"上の行ほど手前に重なります。行をドラッグして並べ替え、左のチェックで表示・非表示。"
                                     u"丸のボタン（単独）でそのレイヤーの素材の全体を、素材の解像度の枠の中に表示します。"
                                     u"その右のボタンで、最初と最後のコンプの枠（原図の枠）を出します。"
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
        self.solo = None
        self._plan_shown = True                               # the layout drawing's frames are wanted (D-54)
        self._plan_available = False                          # the solo layer's whole source is shown
        self._drawn = set()                                   # drawn when nothing is solo
        self._drawable = set()                                # drawn when shown (or solo)

    def set_editing(self, layer_id) -> None:
        """Mark the layer edited in the viewer (bold, "（編集中）"; a symbol was a box in mayapy's font)."""
        self.editing = layer_id
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            mine = item.data(EYE, ID_ROLE) == layer_id
            font = item.font(NAME)
            font.setBold(mine)
            item.setFont(NAME, font)
            name = item.data(NAME, ID_ROLE) or item.text(NAME)
            item.setData(NAME, ID_ROLE, name)
            item.setText(NAME, (name + u"（編集中）") if mine else name)

    def set_solo(self, layer_id) -> None:
        """Show which row is solo (D-49): its button down, the other rows greyed (they are not drawn)."""
        self.solo = layer_id
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            lid = item.data(EYE, ID_ROLE)
            button = self.tree.itemWidget(item, SOLO)
            if button is not None:
                button.blockSignals(True)
                button.setChecked(lid == layer_id)
                button.blockSignals(False)
            plan = self.tree.itemWidget(item, PLAN)
            if plan is not None:                                  # only with this row's solo on (D-54)
                on = lid == layer_id and self._plan_available
                plan.blockSignals(True)
                plan.setEnabled(on)
                plan.setChecked(on and self._plan_shown)
                plan.blockSignals(False)
            dim = lid not in self._drawn if layer_id is None else lid != layer_id
            for col in range(NUMBER, len(COLUMNS)):
                item.setForeground(col, QtGui.QBrush(QtGui.QColor("#7a7a7a")) if dim else QtGui.QBrush())

    def set_plan(self, shown: bool, available: bool) -> None:
        """The layout drawing's frames: wanted, and possible now. set_solo shows them on the rows (D-54)."""
        self._plan_shown, self._plan_available = bool(shown), bool(available)

    def _on_plan(self, shown: bool) -> None:
        self._plan_shown = shown
        self.plan_requested.emit(shown)

    def _plan_button(self) -> QtWidgets.QToolButton:
        button = QtWidgets.QToolButton()
        button.setIcon(_plan_icon())
        button.setIconSize(QtCore.QSize(16, 16))
        button.setFixedHeight(MARK_HEIGHT)
        button.setAccessibleName(u"原図の枠")
        button.setCheckable(True)
        button.setAutoRaise(False)
        button.setEnabled(False)
        button.setToolTip(PLAN_TIP)
        button.setStyleSheet("QToolButton { padding: 0 2px; } "
                             "QToolButton:checked { background: #5285a6; border: 1px solid #7fb0cf; }")
        button.toggled.connect(self._on_plan)
        return button

    def _on_clicked(self, item, column):
        if column not in (EYE, SOLO, PLAN):                      # the eye toggles, it does not choose
            self.editing_requested.emit(item.data(EYE, ID_ROLE))

    def _solo_button(self, layer_id: str, drawable: bool) -> QtWidgets.QToolButton:
        button = QtWidgets.QToolButton()
        button.setIcon(_solo_icon())
        button.setIconSize(QtCore.QSize(16, 16))
        button.setFixedHeight(MARK_HEIGHT)
        button.setAccessibleName(u"単独")
        button.setCheckable(True)
        button.setAutoRaise(False)
        button.setEnabled(drawable)
        button.setToolTip(SOLO_TIP if drawable else u"カメラか表示するオブジェクトがないので、単独で表示できません")
        button.setStyleSheet("QToolButton { padding: 0 2px; } "
                             "QToolButton:checked { background: #5285a6; border: 1px solid #7fb0cf; }")
        button.toggled.connect(lambda on: self.solo_requested.emit(layer_id if on else None))
        return button

    def set_data(self, store: dict) -> None:
        self._filling = True
        try:
            current = self.selected_id()
            self.tree.clear()
            drawable = self._drawable = set(s["id"] for s in core_lm.stack(dict(store, maya_layers=[
                dict(layer, visible=True) for layer in store["maya_layers"]])))
            self._drawn = set(s["id"] for s in core_lm.stack(store))
            for i, layer in enumerate(store["maya_layers"]):
                links = core_lm.links_of(store, layer["id"])
                cam = core_lm.driven_camera(layer)
                resolution = core_lm.layer_resolution(store, layer["id"])
                item = QtWidgets.QTreeWidgetItem([
                    "", "", "", str(i + 1), layer["name"], core_lm.resolution_text(resolution),
                    _transform_name(cam["camera"]) if cam["camera"] else u"（カメラなし）",
                    u", ".join(m["ae"].get("layer") or "?" for m in links) or u"―",
                    str(len(layer.get("objects") or []))])
                item.setData(EYE, ID_ROLE, layer["id"])
                item.setFlags((item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled)
                              & ~Qt.ItemFlag.ItemIsDropEnabled)
                item.setCheckState(EYE, Qt.CheckState.Checked if layer.get("visible", True) else Qt.CheckState.Unchecked)
                item.setIcon(NAME, _swatch(LABEL_COLORS[i % len(LABEL_COLORS)]))
                if layer["id"] not in drawable:
                    item.setToolTip(NAME, u"カメラか表示するオブジェクトがないので描きません")
                item.setToolTip(RESOLUTION, u"AE の素材の大きさ（プリコンポはそのコンポ、素材のないレイヤーは入っているコンポの"
                                            u"大きさ）。レイヤーマップで「AE のレイヤーを読み込む」を押すと更新します"
                                if resolution else u"AE の解像度がまだありません（AE のレイヤーにつなぐと受け取ります）")
                self.tree.addTopLevelItem(item)
                self.tree.setItemWidget(item, SOLO, self._solo_button(layer["id"], layer["id"] in drawable))
                self.tree.setItemWidget(item, PLAN, self._plan_button())
                if layer["id"] == current:
                    item.setSelected(True)
            self.set_editing(self.editing)
            self.set_solo(self.solo)
        finally:
            self._filling = False

    def order(self) -> List[str]:
        return [self.tree.topLevelItem(i).data(0, ID_ROLE) for i in range(self.tree.topLevelItemCount())]

    def selected_id(self):
        items = self.tree.selectedItems()
        return items[0].data(0, ID_ROLE) if items else None

    def _on_drop(self):
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            item.setText(NUMBER, str(i + 1))
            if self.tree.itemWidget(item, SOLO) is None:          # a moved row loses its button
                lid = item.data(EYE, ID_ROLE)
                self.tree.setItemWidget(item, SOLO, self._solo_button(lid, lid in self._drawable))
                self.tree.setItemWidget(item, PLAN, self._plan_button())
        self.set_solo(self.solo)
        self.order_changed.emit(self.order())

    def menu_for(self, item) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu(self)
        layer_id = item.data(0, ID_ROLE)
        action = menu.addAction(u"このレイヤーのアニメーションを転送…")
        action.setEnabled(item.text(AE_LAYER) != u"―")           # no AE layer linked
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
