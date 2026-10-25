"""The layer map's node editor (D-28): AE layers on the left, SyncBridge's Maya layers on the right,
a wire for each link (core.layer_mapping).

Qt only (PySide2 for Maya 2023/2024, PySide6 for Maya 2025+); Maya is not imported here, so the
editor can be shown outside Maya (mocks, tests). The window that talks to Maya connects the signals
of LayerMapEditor (layer_map_window.py).

    editor = LayerMapEditor()
    editor.set_data(ae_info, store)       # SBCep.layersInfo() (or None), the stored layer map
    editor.link_requested.connect(...)    # (ae dict for core.layer_mapping.connect, Maya layer id)
"""
from __future__ import annotations

from typing import Dict, List, Optional

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

from syncbridge.core import layer_mapping as core_lm

Qt = QtCore.Qt

KIND_LABELS = {"still": u"静止画", "sequence": u"連番", "movie": u"動画", "comp": u"コンポ", "solid": u"平面",
               "null": u"ヌル", "camera": u"カメラ", "light": u"ライト", "text": u"テキスト",
               "shape": u"シェイプ", "other": u"その他"}
# Layers with pictures: shown unless "すべてのレイヤー" is on.
FOOTAGE_KINDS = ("still", "sequence", "movie", "comp", "solid")
KIND_COLORS = {"still": "#3f8f8a", "sequence": "#4a72b8", "movie": "#c07a35", "comp": "#8a5ab0",
               "solid": "#7a7a7a"}
METHOD_LABELS = {"film_offset": "Film Offset", "film_translate": "Film Translate", "pan_zoom": "2D Pan/Zoom",
                 "film_roll": u"Film Translate・Scale・Roll"}
METHOD_SHORT = {"film_offset": "Film Offset", "film_translate": "Film Translate", "pan_zoom": "Pan/Zoom",
                "film_roll": "FT+Scale+Roll"}

C_VIEW = QtGui.QColor("#262626")
C_GRID = QtGui.QColor("#2e2e2e")
C_NODE = QtGui.QColor("#3c3c3c")
C_TEXT = QtGui.QColor("#dddddd")
C_DIM = QtGui.QColor("#9a9a9a")
C_MAYA = QtGui.QColor("#4f8a4a")
C_MAYA_VIEW = QtGui.QColor("#6aa860")       # the layer shown in the view
C_MISSING = QtGui.QColor("#5a5a5a")
C_WIRE = QtGui.QColor("#d8b04a")
C_WARN = QtGui.QColor("#e08a40")
C_BAD = QtGui.QColor("#d05a50")
C_SELECT = QtGui.QColor("#5aa0e0")

NODE_W = 230
HEADER_H = 22
LINE_H = 17
PORT_R = 6
AE_X, MAYA_X = 0, 430
NEST_INDENT = 18         # px per precomp level (D-37)
PAN_ROOM = 2000          # px of scene around the nodes the middle drag can move into
GAP = 14


def ae_key(ae: dict):
    """What identifies an AE layer (core.layer_mapping.matches): ids when known, else names, and the
    precomp layers above it (D-37)."""
    if ae.get("layer_id") is not None:
        return ("id", ae.get("comp_id"), ae.get("layer_id"), core_lm.via_key(ae))
    return ("name", ae.get("comp"), ae.get("layer"), core_lm.via_key(ae))


def ae_title(ae: dict) -> str:
    """'SC_PRE › BG' for a layer inside a precomp."""
    return u" › ".join([v.get("layer") or "?" for v in ae.get("via") or []] + [ae.get("layer") or "?"])


class Node(QtWidgets.QGraphicsItem):
    """A box with a coloured header and a few lines of text; `side` is where its port is."""

    def __init__(self, kind: str, key, title: str, lines: List[str], color: QtGui.QColor, side: str,
                 dim: bool = False):
        super().__init__()
        self.kind, self.key, self.title, self.lines, self.color, self.side, self.dim = (
            kind, key, title, lines, color, side, dim)
        self.wires: List["Wire"] = []
        self.height = HEADER_H + 6 + LINE_H * max(1, len(lines))
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def boundingRect(self):
        return QtCore.QRectF(-PORT_R - 2, -2, NODE_W + 2 * PORT_R + 4, self.height + 4)

    def port_pos(self) -> QtCore.QPointF:
        x = NODE_W if self.side == "right" else 0
        return self.mapToScene(QtCore.QPointF(x, HEADER_H / 2.0))

    def port_hit(self, scene_pos: QtCore.QPointF) -> bool:
        d = scene_pos - self.port_pos()
        return d.x() * d.x() + d.y() * d.y() <= (PORT_R + 4) ** 2

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        body = QtCore.QRectF(0, 0, NODE_W, self.height)
        painter.setPen(QtGui.QPen(C_SELECT if self.isSelected() else QtGui.QColor("#1a1a1a"),
                                  2 if self.isSelected() else 1))
        painter.setBrush(C_NODE.darker(115) if self.dim else C_NODE)
        painter.drawRoundedRect(body, 4, 4)
        head = QtGui.QPainterPath()
        head.addRoundedRect(QtCore.QRectF(0, 0, NODE_W, HEADER_H), 4, 4)
        head.addRect(QtCore.QRectF(0, HEADER_H - 4, NODE_W, 4))
        painter.fillPath(head.simplified(), C_MISSING if self.dim else self.color)
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(C_TEXT)
        painter.drawText(QtCore.QRectF(8, 0, NODE_W - 16, HEADER_H),
                         int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                         painter.fontMetrics().elidedText(self.title, Qt.TextElideMode.ElideRight, NODE_W - 16))
        font.setBold(False)
        painter.setFont(font)
        for i, line in enumerate(self.lines):
            painter.setPen(C_WARN if line.startswith(u"⚠") else C_DIM)
            painter.drawText(QtCore.QRectF(8, HEADER_H + 3 + i * LINE_H, NODE_W - 16, LINE_H),
                             int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                             painter.fontMetrics().elidedText(line, Qt.TextElideMode.ElideRight, NODE_W - 16))
        x = NODE_W if self.side == "right" else 0
        painter.setPen(QtGui.QPen(QtGui.QColor("#1a1a1a"), 1))
        painter.setBrush(C_WIRE if self.wires else QtGui.QColor("#8a8a8a"))
        painter.drawEllipse(QtCore.QPointF(x, HEADER_H / 2.0), PORT_R, PORT_R)

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for w in self.wires:
                w.update_path()
        return super().itemChange(change, value)


class Wire(QtWidgets.QGraphicsPathItem):
    """A link from an AE node's port to a Maya layer node's port, with its mode and method."""

    def __init__(self, mapping: Optional[dict], src: Node, dst: Optional[Node] = None):
        super().__init__()
        self.mapping, self.src, self.dst = mapping, src, dst
        self.end = QtCore.QPointF()
        self.label = ""
        self.state = "ok"
        self.setZValue(-1)
        if mapping is not None:
            self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            self.label = u"%s %s" % (core_lm.MODE_LABELS[core_lm.mode_of(mapping)],
                                     METHOD_SHORT.get(mapping["method"], mapping["method"]))
            if core_lm.mode_of(mapping) == "relative" and not mapping.get("reference"):
                self.state, self.label = "warn", self.label + u"・基準なし"
            if not mapping.get("enabled", True):
                self.state, self.label = "off", self.label + u"・無効"
            self.setToolTip(core_lm.describe(mapping))

    def update_path(self):
        a = self.src.port_pos()
        b = self.dst.port_pos() if self.dst is not None else self.end
        dx = max(60.0, abs(b.x() - a.x()) * 0.5)
        path = QtGui.QPainterPath(a)
        path.cubicTo(a + QtCore.QPointF(dx, 0), b - QtCore.QPointF(dx, 0), b)
        self.setPath(path)

    def shape(self):
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(12)
        return stroker.createStroke(self.path())

    def boundingRect(self):
        return super().boundingRect().adjusted(-80, -20, 80, 20)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        color = {"ok": C_WIRE, "warn": C_WARN, "bad": C_BAD, "off": C_MISSING}[self.state]
        if self.isSelected():
            color = C_SELECT
        pen = QtGui.QPen(color, 3 if self.isSelected() else 2)
        if self.state in ("off", "warn") or self.mapping is None:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())
        if self.label:
            # Next to the AE port: wires meet near the Maya side, but start one per AE node.
            start = self.src.port_pos()
            fm = painter.fontMetrics()
            w = fm.horizontalAdvance(self.label) + 12 if hasattr(fm, "horizontalAdvance") else fm.width(self.label) + 12
            box = QtCore.QRectF(start.x() + PORT_R + 6, start.y() - 9, w, 18)
            painter.setPen(QtGui.QPen(color, 1))
            painter.setBrush(QtGui.QColor("#202020"))
            painter.drawRoundedRect(box, 9, 9)
            painter.setPen(C_TEXT)
            painter.drawText(box, int(Qt.AlignmentFlag.AlignCenter), self.label)


class LayerMapScene(QtWidgets.QGraphicsScene):
    link_requested = QtCore.Signal(object, str)        # (AE node key, Maya layer id)
    layer_double_clicked = QtCore.Signal(str)          # Maya layer id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag: Optional[Wire] = None

    def mouseDoubleClickEvent(self, event):
        node = self._node_at(event.scenePos(), "maya")
        if node is not None:
            self.layer_double_clicked.emit(node.key)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, C_VIEW)
        painter.setPen(QtGui.QPen(C_GRID, 1))
        step = 20
        x = int(rect.left()) - int(rect.left()) % step
        while x < rect.right():
            painter.drawLine(QtCore.QPointF(x, rect.top()), QtCore.QPointF(x, rect.bottom()))
            x += step
        y = int(rect.top()) - int(rect.top()) % step
        while y < rect.bottom():
            painter.drawLine(QtCore.QPointF(rect.left(), y), QtCore.QPointF(rect.right(), y))
            y += step

    def _node_at(self, pos, kind: str) -> Optional[Node]:
        for item in self.items(pos):
            if isinstance(item, Node) and item.kind == kind:
                return item
        for item in self.items():                         # the port sticks out of the node's box
            if isinstance(item, Node) and item.kind == kind and item.port_hit(pos):
                return item
        return None

    def mousePressEvent(self, event):
        node = self._node_at(event.scenePos(), "ae")
        if event.button() == Qt.MouseButton.LeftButton and node is not None and not node.dim \
                and node.port_hit(event.scenePos()):
            self._drag = Wire(None, node)
            self._drag.end = event.scenePos()
            self._drag.update_path()
            self.addItem(self._drag)
            event.accept()                 # the view must not start anything else with this press
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            self._drag.end = event.scenePos()
            self._drag.update_path()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag is not None:
            src = self._drag.src
            self.removeItem(self._drag)
            self._drag = None
            target = self._node_at(event.scenePos(), "maya")
            if target is not None:
                self.link_requested.emit(src.key, target.key)
            return
        super().mouseReleaseEvent(event)


def _point(event):
    """The mouse position in the viewport (PySide6: position(); PySide2: pos())."""
    return event.position().toPoint() if hasattr(event, "position") else event.pos()


class LayerMapView(QtWidgets.QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        # no rubber band: it showed up while wiring and got in the way (the user, 2026-10-25)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        # middle drag tracks the view like Maya's Node Editor (the user, 2026-10-25): no scroll bars, and
        # the scene rect has room around the nodes (fit_room) so the view can move past them
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._track = None
        self._centered = False
        self._bounds = None

    def sizeHint(self):
        # the default is the scene rect (with PAN_ROOM: most of the screen), which made the window huge
        # (the user, 2026-10-25)
        return QtCore.QSize(560, 360)

    def fit_room(self, bounds):
        """Grow (never shrink: the view must not jump) the scene rect to the nodes plus PAN_ROOM; centers
        on the nodes the first time."""
        room = bounds.adjusted(-PAN_ROOM, -PAN_ROOM, PAN_ROOM, PAN_ROOM)
        rect = self.scene().sceneRect()
        self.scene().setSceneRect(room if not self._centered else rect.united(room))
        self._bounds = bounds
        if not self._centered and self.isVisible() and not bounds.isEmpty():
            self.centerOn(bounds.center())
            self._centered = True

    def showEvent(self, event):
        super().showEvent(event)
        if not self._centered and self._bounds is not None and not self._bounds.isEmpty():
            self.centerOn(self._bounds.center())       # set_data may come before the view has its size
            self._centered = True

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._track = _point(event)
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._track is not None:
            delta = _point(event) - self._track
            self._track = _point(event)
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._track is not None and event.button() == Qt.MouseButton.MiddleButton:
            self._track = None
            self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        scale = self.transform().m11() * factor
        if 0.3 < scale < 3.0:
            self.scale(factor, factor)


class LayerMapEditor(QtWidgets.QWidget):
    """Toolbar, the node graph and an inspector for what is selected. Emits what the user asks for;
    the owner changes the store and calls set_data again."""

    reload_requested = QtCore.Signal()                    # AE のレイヤーを読み込む
    new_method_changed = QtCore.Signal(str)               # method for new links
    new_mode_changed = QtCore.Signal(str)                 # mode for new links (relative / source, D-39)
    add_layer_requested = QtCore.Signal()                 # Maya レイヤーを追加
    link_requested = QtCore.Signal(object, str)           # (ae dict for core.layer_mapping.connect, layer id)
    unlink_requested = QtCore.Signal(str)                 # mapping id
    method_requested = QtCore.Signal(str, str)            # mapping id, method
    mode_requested = QtCore.Signal(str, str)              # mapping id, mode
    reset_reference_requested = QtCore.Signal(str)        # mapping id
    record_reference_requested = QtCore.Signal(str)       # mapping id: the reference from AE at this frame (D-37)
    motion_requested = QtCore.Signal(str)                 # mapping id: transfer the AE layer's motion (Phase 3)
    motion_all_requested = QtCore.Signal()                # every link at once
    view_layer_requested = QtCore.Signal(str)             # Maya layer id: show it in the view (D-31)
    view_all_requested = QtCore.Signal()                  # Isolate Select off
    viewer_requested = QtCore.Signal()                    # open the SyncBridge viewer (D-33)
    rename_layer_requested = QtCore.Signal(str, str)      # layer id, name
    camera_requested = QtCore.Signal(str)                 # layer id: use the selected camera
    add_objects_requested = QtCore.Signal(str)            # layer id: add the selected objects
    remove_objects_requested = QtCore.Signal(str, list)   # layer id, object uuids
    select_objects_requested = QtCore.Signal(str)         # layer id: select its camera and objects in Maya
    remove_layer_requested = QtCore.Signal(str)           # layer id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ae_info: Optional[dict] = None
        self.store = core_lm.empty_store()
        self.viewing: Optional[str] = None               # the Maya layer shown in the view (D-31)
        self._ae_layers: Dict[object, dict] = {}
        self._positions: Dict[object, QtCore.QPointF] = {}

        self.reload_btn = QtWidgets.QPushButton(u"AE のレイヤーを読み込む")
        self.reload_btn.clicked.connect(self.reload_requested.emit)
        self.add_btn = QtWidgets.QPushButton(u"Maya レイヤーを追加")
        self.add_btn.clicked.connect(self.add_layer_requested.emit)
        self.all_check = QtWidgets.QCheckBox(u"すべてのレイヤー")
        self.all_check.setToolTip(u"オフのときは画像のあるレイヤー（静止画・連番・動画・コンポ・平面）だけを表示します。")
        self.all_check.toggled.connect(lambda _: self.rebuild())
        self.comp_label = QtWidgets.QLabel(u"AE: 未読み込み")
        self.comp_label.setStyleSheet("color: #9a9a9a;")
        self.new_method = QtWidgets.QComboBox()
        for method in ("pan_zoom", "film_roll", "film_translate", "film_offset"):
            self.new_method.addItem(METHOD_LABELS[method], method)
        self.new_method.setToolTip(u"新しくつなぐ線の方式（相対モードで始まります。あとから線ごとに変えられます）\n"
                                   u"2D Pan/Zoom: 平行移動と拡大縮小\n"
                                   u"Film Translate・Scale・Roll: 平行移動・拡大縮小・回転\n"
                                   u"Film Translate / Film Offset: 平行移動だけ")
        self.new_method.activated.connect(lambda i: self.new_method_changed.emit(self.new_method.itemData(i)))
        self.motion_all_btn = QtWidgets.QPushButton(u"すべてのアニメーションを転送…")
        self.motion_all_btn.setToolTip(u"すべての接続について、AE のレイヤーの動きを範囲の各フレームのキーとして"
                                       u"それぞれのカメラに打ちます（範囲の指定と確認は 1 回。Ctrl+Z 1 回で全部戻ります）")
        self.motion_all_btn.clicked.connect(self.motion_all_requested.emit)
        bar = QtWidgets.QHBoxLayout()                       # AE side
        for w in (self.reload_btn, self.all_check, self.comp_label):
            bar.addWidget(w)
        bar.addStretch(1)
        self.new_mode = QtWidgets.QComboBox()
        for mode in ("source", "relative"):
            self.new_mode.addItem(core_lm.MODE_LABELS[mode], mode)
        self.new_mode.setToolTip(u"素材カメラ: AE の素材を書き出したカメラを Maya レイヤーのカメラにすると、素材の大きさから直接合わせます"
                                 u"（基準を合わせる手間なし）\n"
                                 u"相対: 基準のフレームで Maya と AE の見え方を合わせて記録し、そこからの動きを足します")
        self.new_mode.activated.connect(lambda i: self.new_mode_changed.emit(self.new_mode.itemData(i)))
        bar2 = QtWidgets.QHBoxLayout()                      # Maya side
        bar2.addWidget(QtWidgets.QLabel(u"新しい接続"))
        bar2.addWidget(self.new_mode)
        bar2.addWidget(self.new_method)
        bar2.addStretch(1)
        self.view_all_btn = QtWidgets.QPushButton(u"表示を戻す")
        self.view_all_btn.setToolTip(u"「このレイヤーで見る」をやめ、ビューにすべてを表示します（カメラはそのまま）")
        self.view_all_btn.clicked.connect(self.view_all_requested.emit)
        self.viewer_btn = QtWidgets.QPushButton(u"ビューアー…")
        self.viewer_btn.setToolTip(u"Maya レイヤーをそれぞれのカメラで描いて AE のように重ねて見るウィンドウを開きます"
                                   u"（下に AE のようなレイヤーの一覧。シーンは変えません）")
        self.viewer_btn.clicked.connect(self.viewer_requested.emit)
        bar2.addWidget(self.viewer_btn)
        bar2.addWidget(self.view_all_btn)
        bar2.addWidget(self.add_btn)
        bar2.addSpacing(12)
        bar2.addWidget(self.motion_all_btn)

        self.scene = LayerMapScene(self)
        self.scene.link_requested.connect(self._on_link)
        self.scene.layer_double_clicked.connect(self.view_layer_requested.emit)
        self.scene.selectionChanged.connect(self._on_selection)
        self.view = LayerMapView(self.scene)
        action_cls = getattr(QtGui, "QAction", None) or QtWidgets.QAction      # PySide6 / PySide2
        delete = action_cls(self.view)
        delete.setShortcuts([QtGui.QKeySequence(Qt.Key.Key_Delete), QtGui.QKeySequence(Qt.Key.Key_Backspace)])
        delete.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        delete.triggered.connect(self._on_delete_key)
        self.view.addAction(delete)

        self.inspector = QtWidgets.QStackedWidget()
        self.inspector.setMinimumWidth(270)
        self.inspector.setMaximumWidth(340)
        self._build_inspector()

        split = QtWidgets.QSplitter()
        split.addWidget(self.view)
        split.addWidget(self.inspector)
        split.setStretchFactor(0, 1)
        self.hint = QtWidgets.QLabel(u"AE のレイヤーの右の ● から Maya レイヤーへドラッグしてつなぎます。"
                                     u"線を選んで Delete で外します。Maya レイヤーのダブルクリックで、そのレイヤーだけをビューに表示。"
                                     u"ホイールで拡大縮小。")
        self.hint.setStyleSheet("color: #9a9a9a;")
        self.hint.setWordWrap(True)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(bar)
        lay.addLayout(bar2)
        lay.addWidget(split, 1)
        lay.addWidget(self.hint)

    def set_new_method(self, method: str) -> None:
        self.new_method.setCurrentIndex(max(0, self.new_method.findData(method)))

    def set_new_mode(self, mode: str) -> None:
        self.new_mode.setCurrentIndex(max(0, self.new_mode.findData(mode)))

    # -- inspector --------------------------------------------------------------------------------------
    def _build_inspector(self):
        empty = QtWidgets.QLabel(u"ノードか線を選ぶと、ここに詳細が出ます。")
        empty.setWordWrap(True)
        empty.setAlignment(Qt.AlignmentFlag.AlignTop)
        empty.setStyleSheet("color: #9a9a9a; padding: 8px;")
        self.inspector.addWidget(empty)

        ae = QtWidgets.QWidget()
        self.ae_text = QtWidgets.QLabel()
        self.ae_text.setWordWrap(True)
        self.ae_text.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.ae_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        QtWidgets.QVBoxLayout(ae).addWidget(self.ae_text, 1)
        self.inspector.addWidget(ae)

        maya = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout()
        self.layer_name = QtWidgets.QLineEdit()
        self.layer_name.editingFinished.connect(self._on_rename)
        self.camera_label = QtWidgets.QLabel()
        self.camera_btn = QtWidgets.QPushButton(u"選択中のカメラにする")
        self.camera_btn.clicked.connect(lambda: self.camera_requested.emit(self._selected_layer_id()))
        form.addRow(u"名前", self.layer_name)
        form.addRow(u"カメラ", self.camera_label)
        form.addRow("", self.camera_btn)
        self.objects = QtWidgets.QListWidget()
        self.objects.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        obj_btns = QtWidgets.QHBoxLayout()
        for text, fn in ((u"選択中を追加", lambda: self.add_objects_requested.emit(self._selected_layer_id())),
                         (u"外す", self._on_remove_objects),
                         (u"Maya で選択", lambda: self.select_objects_requested.emit(self._selected_layer_id()))):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(fn)
            obj_btns.addWidget(b)
        self.remove_layer_btn = QtWidgets.QPushButton(u"このレイヤーを削除")
        self.remove_layer_btn.clicked.connect(lambda: self.remove_layer_requested.emit(self._selected_layer_id()))
        self.view_btn = QtWidgets.QPushButton(u"このレイヤーで見る")
        self.view_btn.setToolTip(u"今のビューを、このレイヤーのカメラ（専用カメラ）にして、表示するオブジェクトだけを見せます"
                                 u"（Isolate Select。シーンは変えません。ノードのダブルクリックでも同じ）")
        self.view_btn.clicked.connect(lambda: self.view_layer_requested.emit(self._selected_layer_id()))
        v = QtWidgets.QVBoxLayout(maya)
        v.addLayout(form)
        v.addWidget(self.view_btn)
        v.addWidget(QtWidgets.QLabel(u"表示するオブジェクト"))
        v.addWidget(self.objects, 1)
        v.addLayout(obj_btns)
        v.addWidget(self.remove_layer_btn)
        self.inspector.addWidget(maya)

        link = QtWidgets.QWidget()
        self.link_text = QtWidgets.QLabel()
        self.link_text.setWordWrap(True)
        self.mode_combo = QtWidgets.QComboBox()
        for mode in core_lm.MODES:
            self.mode_combo.addItem(core_lm.MODE_LABELS[mode], mode)
        self.mode_combo.activated.connect(
            lambda i: self.mode_requested.emit(self._selected_mapping_id(), self.mode_combo.itemData(i)))
        self.method_combo = QtWidgets.QComboBox()
        for method in ("pan_zoom", "film_roll", "film_translate", "film_offset"):
            self.method_combo.addItem(METHOD_LABELS[method], method)
        self.method_combo.activated.connect(
            lambda i: self.method_requested.emit(self._selected_mapping_id(), self.method_combo.itemData(i)))
        self.reset_btn = QtWidgets.QPushButton(u"基準をやり直す")
        self.reset_btn.clicked.connect(lambda: self.reset_reference_requested.emit(self._selected_mapping_id()))
        self.record_btn = QtWidgets.QPushButton(u"基準を記録（今のフレーム）")
        self.record_btn.setToolTip(u"Maya の今のフレームにあたる AE の時間で、AE のレイヤーの位置を読み、基準として記録します"
                                   u"（Maya と AE の見え方を合わせてから。プリコンポの中のレイヤーはこれで記録します）")
        self.record_btn.clicked.connect(lambda: self.record_reference_requested.emit(self._selected_mapping_id()))
        self.unlink_btn = QtWidgets.QPushButton(u"接続を外す")
        self.unlink_btn.clicked.connect(lambda: self.unlink_requested.emit(self._selected_mapping_id()))
        self.anim_btn = QtWidgets.QPushButton(u"アニメーションを転送…")
        self.anim_btn.setToolTip(u"AE のレイヤーの動き（位置・スケール・回転）を、範囲の各フレームのキーとして"
                                 u"カメラに打ちます（相対モードは先に基準が要ります）")
        self.anim_btn.clicked.connect(lambda: self.motion_requested.emit(self._selected_mapping_id()))
        form = QtWidgets.QFormLayout()
        form.addRow(u"モード", self.mode_combo)
        form.addRow(u"方式", self.method_combo)
        v = QtWidgets.QVBoxLayout(link)
        v.addWidget(self.link_text)
        v.addLayout(form)
        v.addWidget(self.record_btn)
        v.addWidget(self.reset_btn)
        v.addWidget(self.unlink_btn)
        v.addSpacing(8)
        v.addWidget(self.anim_btn)
        v.addStretch(1)
        self.inspector.addWidget(link)

    def _selected(self):
        items = self.scene.selectedItems()
        return items[0] if len(items) == 1 else None

    def _selected_layer_id(self) -> str:
        item = self._selected()
        return item.key if isinstance(item, Node) and item.kind == "maya" else ""

    def _selected_mapping_id(self) -> str:
        item = self._selected()
        return item.mapping["id"] if isinstance(item, Wire) and item.mapping else ""

    def _on_selection(self):
        item = self._selected()
        if isinstance(item, Wire) and item.mapping:
            self._show_link(item.mapping)
        elif isinstance(item, Node) and item.kind == "maya":
            self._show_layer(core_lm.maya_layer(self.store, item.key))
        elif isinstance(item, Node):
            self._show_ae(item)
        else:
            self.inspector.setCurrentIndex(0)

    def _show_ae(self, node: Node):
        layer = self._ae_layers.get(node.key)
        if layer is None:
            m = self._mapping_of_key(node.key)
            self.ae_text.setText(u"<b>%s</b><br>現在の AE のコンポにありません（コンポ「%s」）。<br>"
                                 u"コンポを開いて「AE のレイヤーを読み込む」を押すか、接続を外してください。"
                                 % (node.title, (m or {}).get("ae", {}).get("comp") or "?"))
        else:
            keyed = [k for k, v in (layer.get("keyed") or {}).items() if v]
            rows = [(u"種類", KIND_LABELS.get(layer.get("kind"), layer.get("kind"))),
                    (u"ソース", layer.get("source") or "-"),
                    (u"サイズ", "%s × %s" % (layer.get("width"), layer.get("height")) if layer.get("width") else "-"),
                    (u"イン / アウト", u"%.2f 秒 / %.2f 秒" % (layer.get("inPoint") or 0, layer.get("outPoint") or 0)),
                    (u"3D", u"はい" if layer.get("threeD") else u"いいえ"),
                    (u"親", layer.get("parent") or "-"),
                    (u"キー", ", ".join(keyed) if keyed else u"なし")]
            self.ae_text.setText(u"<b>%s</b><table>%s</table>" % (node.title, "".join(
                u"<tr><td style='color:#9a9a9a;padding-right:8px'>%s</td><td>%s</td></tr>" % r for r in rows)))
        self.inspector.setCurrentIndex(1)

    def _show_layer(self, layer: Optional[dict]):
        if layer is None:
            self.inspector.setCurrentIndex(0)
            return
        self.layer_name.setText(layer["name"])
        self.camera_label.setText(_camera_text(layer) if layer.get("camera")
                                  else u"<span style='color:#e08a40'>未設定</span>")
        self.camera_label.setToolTip(u"元のカメラ → SyncBridge の専用カメラ（元のカメラの子。AE の動きはこちらに入ります）"
                                     if layer.get("layer_camera") else u"")
        self.objects.clear()
        for obj in layer.get("objects") or []:
            item = QtWidgets.QListWidgetItem(core_lm.short_name(obj.get("name")))
            item.setToolTip(obj.get("name") or "")
            item.setData(Qt.ItemDataRole.UserRole, obj.get("uuid"))
            self.objects.addItem(item)
        self.inspector.setCurrentIndex(2)

    def _show_link(self, mapping: dict):
        layer = core_lm.maya_layer(self.store, mapping.get("maya_layer")) or {}
        ref = mapping.get("reference")
        state = u"基準: %s" % (u"記録済み（%.2f 秒）" % ref["comp_time"] if ref and ref.get("comp_time") is not None
                               else u"記録済み" if ref else u"<span style='color:#e0a040'>なし（次の送信で記録）</span>")
        if core_lm.mode_of(mapping) == "absolute":
            state = u"BG: %s" % core_lm.short_name((mapping.get("maya") or {}).get("bg"))
        self.link_text.setText(u"<b>%s</b> → <b>%s</b><br>%s" % (
            ae_title(mapping["ae"]), layer.get("name", "?"), state))
        self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData(core_lm.mode_of(mapping))))
        self.method_combo.setCurrentIndex(max(0, self.method_combo.findData(mapping["method"])))
        self.reset_btn.setEnabled(core_lm.mode_of(mapping) == "relative")
        self.record_btn.setEnabled(core_lm.mode_of(mapping) == "relative")
        if core_lm.mode_of(mapping) == "source":
            self.link_text.setText(self.link_text.text().split("<br>")[0] +
                                   u"<br>素材カメラ: 素材を書き出したカメラと素材の大きさから直接合わせます（基準は不要）")
        self.inspector.setCurrentIndex(3)

    def _on_rename(self):
        layer_id = self._selected_layer_id()
        layer = core_lm.maya_layer(self.store, layer_id)
        name = self.layer_name.text().strip()
        if layer is not None and name and name != layer["name"]:
            self.rename_layer_requested.emit(layer_id, name)

    def _on_remove_objects(self):
        uuids = [i.data(Qt.ItemDataRole.UserRole) for i in self.objects.selectedItems()]
        if uuids:
            self.remove_objects_requested.emit(self._selected_layer_id(), uuids)

    def _on_link(self, ae_key_value, layer_id: str):
        layer = self._ae_layers.get(ae_key_value)
        if layer is not None and self.ae_info:
            self.link_requested.emit(core_lm.ae_from_layers_info(self.ae_info["comp"], layer), layer_id)

    def _on_delete_key(self):
        if self._selected_mapping_id():
            self.unlink_requested.emit(self._selected_mapping_id())

    # -- graph ------------------------------------------------------------------------------------------
    def _mapping_of_key(self, key) -> Optional[dict]:
        for m in self.store["mappings"]:
            if ae_key(m["ae"]) == key:
                return m
        return None

    def set_data(self, ae_info: Optional[dict], store: dict) -> None:
        """Show these AE layers (SBCep.layersInfo(), None = not loaded) and the stored layer map."""
        if ae_info is not None:
            self.ae_info = ae_info
        self.store = store
        self.rebuild()

    def rebuild(self) -> None:
        keep = self._selected()
        keep_key = (keep.mapping["id"] if isinstance(keep, Wire) and keep.mapping
                    else keep.key if isinstance(keep, Node) else None)
        for item in self.scene.items():
            if isinstance(item, Node):
                self._positions[(item.kind, item.key)] = item.pos()
        self.scene.clear()
        nodes: Dict[object, Node] = {}
        comp = (self.ae_info or {}).get("comp") or {}
        if self.ae_info:
            self.comp_label.setText(u"AE: %s（%s×%s・%s fps・%d レイヤー）" % (
                comp.get("name"), comp.get("width"), comp.get("height"), _fps(comp.get("frameRate")),
                len(self.ae_info.get("layers") or [])))
        self._ae_layers = {}
        linked = set(ae_key(m["ae"]) for m in self.store["mappings"])
        y = 0.0
        for layer in (self.ae_info or {}).get("layers") or []:
            key = ae_key(core_lm.ae_from_layers_info(comp, layer))
            self._ae_layers[key] = layer
            if layer.get("kind") not in FOOTAGE_KINDS and not self.all_check.isChecked() and key not in linked:
                continue
            kind = KIND_LABELS.get(layer.get("kind"), layer.get("kind") or "?")
            size = "%s×%s" % (layer["width"], layer["height"]) if layer.get("width") else ""
            lines = [u"%s　%s" % (kind, size), layer.get("source") or ""]
            if not layer.get("enabled", True):
                lines[0] += u"　（非表示）"
            depth = len(layer.get("via") or [])
            title = u"%d  %s" % (layer.get("index", 0), layer.get("name")) if not depth else \
                u"%d  %s" % (layer.get("index", 0), ae_title(core_lm.ae_from_layers_info(comp, layer)))
            node = Node("ae", key, title, [l for l in lines if l],
                        QtGui.QColor(KIND_COLORS.get(layer.get("kind"), "#6a6a6a")), "right")
            y = self._place(node, nodes, AE_X + NEST_INDENT * depth, y)       # inside a precomp: indented (D-37)
        for m in self.store["mappings"]:                   # linked AE layers that are not in this comp
            key = ae_key(m["ae"])
            if ("ae", key) in nodes:
                continue
            node = Node("ae", key, ae_title(m["ae"]),
                        [u"⚠ 現在のコンプにありません", u"コンポ: %s" % (m["ae"].get("comp") or "?")],
                        C_MISSING, "right", dim=True)
            y = self._place(node, nodes, AE_X, y)
        y = 0.0
        for layer in self.store["maya_layers"]:
            objects = layer.get("objects") or []
            lines = [u"カメラ: %s" % _short_camera(layer.get("camera")) if layer.get("camera") else u"⚠ カメラ未設定"]
            if layer.get("layer_camera"):
                lines.append(u"専用カメラ: %s" % _short_camera(layer["layer_camera"]))
            names = [core_lm.short_name(o.get("name")) for o in objects]
            lines.append(u"オブジェクト: %d" % len(objects) + (u"（%s）" % ", ".join(names[:3]) +
                                                              (u" ほか %d" % (len(names) - 3) if len(names) > 3 else "")
                                                              if names else ""))
            if len(core_lm.links_of(self.store, layer["id"])) > 1:
                lines.append(u"⚠ 複数の AE レイヤーがつながっています")
            title = layer["name"] + (u"　［表示中］" if layer["id"] == self.viewing else u"")
            node = Node("maya", layer["id"], title, lines, C_MAYA_VIEW if layer["id"] == self.viewing else C_MAYA, "left")
            y = self._place(node, nodes, MAYA_X, y)
        conflicts = set()
        for m in self.store["mappings"]:
            if core_lm.camera_conflicts(self.store["mappings"], m):
                conflicts.add(m["id"])
        for m in self.store["mappings"]:
            src, dst = nodes.get(("ae", ae_key(m["ae"]))), nodes.get(("maya", m.get("maya_layer")))
            if src is None or dst is None:
                continue
            wire = Wire(m, src, dst)
            if m["id"] in conflicts:
                wire.state = "bad"
                wire.setToolTip(u"同じカメラを同じ方式で動かす接続がほかにあります。どちらかを外すか方式を変えてください。")
            src.wires.append(wire)
            dst.wires.append(wire)
            self.scene.addItem(wire)
            wire.update_path()
            if keep_key == m["id"]:
                wire.setSelected(True)
        for node in nodes.values():
            if keep_key is not None and node.key == keep_key:
                node.setSelected(True)
        self.motion_all_btn.setEnabled(bool(self.store["mappings"]))
        self.view.fit_room(self.scene.itemsBoundingRect())
        self._on_selection()

    def _place(self, node: Node, nodes: dict, x: float, y: float) -> float:
        self.scene.addItem(node)
        node.setPos(self._positions.get((node.kind, node.key), QtCore.QPointF(x, y)))
        nodes[(node.kind, node.key)] = node
        return y + node.height + GAP


def _short_camera(path) -> str:
    return core_lm.short_name(path).replace("Shape", "")


def _camera_text(layer: dict) -> str:
    """'SHOT_CAM → SB_BG_CAM' (original → dedicated camera, D-29), or the camera alone."""
    if layer.get("layer_camera"):
        return u"%s → %s" % (_short_camera(layer["camera"]), _short_camera(layer["layer_camera"]))
    return _short_camera(layer.get("camera"))


def _fps(rate) -> str:
    if rate is None:
        return "?"
    return ("%.3f" % rate).rstrip("0").rstrip(".")
