"""The SyncBridge viewer (D-33): a Maya view that stacks the Maya layers like AE (the layer stack
render override, D-32) and, below it, an AE-like layer list to order and show / hide them.

    import syncbridge_maya.viewer_window as vw
    vw.show()

The view is a model panel made by this window (H-MY-34: a modelPanel can live in a Qt layout of our
window). Each layer is drawn through its own dedicated camera. One layer is the editing one (D-44): the
panel looks through the viewer camera that follows it (viewer_camera.py), so Maya's selection, manipulators
and 2D Pan/Zoom tool work in that layer's picture; the other layers follow the same 2D pan / zoom. A click
on another layer's mesh makes that layer the editing one (viewer_pick.py). Order and visibility are saved
in the scene (one undo each). The viewer camera is not saved and goes when the window closes.
"""
from __future__ import annotations

from typing import Optional

from maya import OpenMayaUI as omui
from maya import cmds

try:
    from PySide6 import QtCore, QtWidgets
    from shiboken6 import getCppPointer, wrapInstance
except ImportError:
    from PySide2 import QtCore, QtWidgets
    from shiboken2 import getCppPointer, wrapInstance

from syncbridge.core import layer_mapping as core_lm

from . import layer_mapping, layer_stack, motion_transfer, service, viewer_camera
from .layer_stack_view import LayerStackList

WINDOW_NAME = "SyncBridgeViewer"
CLICK_SLOP_PX = 4               # a press and release this close is a click, not a drag (manipulator, marquee)
_window = None


def _label(camera_path: str) -> str:
    """Transform name of a camera shape path (what the Outliner shows)."""
    parts = camera_path.split("|")
    return parts[-2] if len(parts) > 1 and parts[-2] else parts[-1]


def _uuid(node: str) -> Optional[str]:
    """The camera transform's UUID (a shape is taken as its transform)."""
    if cmds.nodeType(node) == "camera":
        node = cmds.listRelatives(node, parent=True, fullPath=True)[0]
    found = cmds.ls(node, uuid=True)
    return found[0] if found else None


def _click_mode(mods) -> Optional[str]:
    """What a left click with these keys does to Maya's selection: "replace", "toggle" (Shift), "add"
    (Ctrl+Shift), "deselect" (Ctrl: never changes the editing layer), or None (Alt moves the camera)."""
    mod = QtCore.Qt.KeyboardModifier
    if mods & mod.AltModifier:
        return None
    if mods & mod.ControlModifier:
        return "add" if mods & mod.ShiftModifier else "deselect"
    return "toggle" if mods & mod.ShiftModifier else "replace"


def _maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr is not None else None


class ViewerWindow(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(WINDOW_NAME)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowType.Window)
        self.setWindowTitle(u"SyncBridge ビューアー")
        self.resize(960, 720)
        self.panel: Optional[str] = None
        self._pane: Optional[str] = None

        self.camera_label = QtWidgets.QLabel()
        map_btn = QtWidgets.QPushButton(u"レイヤーマップ…")
        map_btn.clicked.connect(self._open_layer_map)
        self.frame_btn = QtWidgets.QPushButton(u"解像度の枠")
        self.frame_btn.setCheckable(True)
        self.frame_btn.setChecked(layer_stack.frame_shown())
        self.frame_btn.setToolTip(u"Maya のレンダー設定の解像度の枠を、ビューアーに出す / 消す。"
                                  u"Maya の解像度ゲートは Overscan を 1.3 にするので、ビューアーでは使いません")
        self.frame_btn.toggled.connect(self._toggle_frame)
        # a frame of any size too (the AE main comp is sometimes a little larger than the picture, 2026-10-27)
        self.custom_btn = QtWidgets.QPushButton(u"任意の枠")
        self.custom_btn.setCheckable(True)
        self.custom_btn.setChecked(layer_stack.custom_frame() is not None)
        self.custom_btn.setToolTip(u"入力した解像度の枠（水色）を出す / 消す。レンダー解像度の枠と同じく中央に、"
                                   u"レンダー解像度を基準の大きさとして描きます")
        self.custom_w, self.custom_h = QtWidgets.QSpinBox(), QtWidgets.QSpinBox()
        for spin, value, tip in ((self.custom_w, layer_stack.custom_size()[0], u"任意の枠の幅（px）"),
                                 (self.custom_h, layer_stack.custom_size()[1], u"任意の枠の高さ（px）")):
            spin.setRange(1, 32768)
            spin.setValue(value)
            spin.setFixedWidth(64)
            spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
            spin.setToolTip(tip)
            spin.editingFinished.connect(self._set_custom)
        self.custom_btn.toggled.connect(self._set_custom)
        self.margin_combo = QtWidgets.QComboBox()
        for value, text in ((1.0, u"なし"), (1.1, u"10%"), (1.2, u"20%"), (1.3, u"30%")):
            self.margin_combo.addItem(text, value)
        self.margin_combo.setToolTip(u"ビューアーだけを少し縮めて枠のまわりを見せます。「ズームを戻す」で戻る大きさにもなります"
                                     u"（カメラの値は変えません。普通のビューと Playblast には影響しません）")
        self.margin_combo.setCurrentIndex(max(0, self.margin_combo.findData(round(layer_stack.margin(), 2))))
        self.margin_combo.activated.connect(self._set_margin)
        # D-44: Maya's 2D Pan/Zoom tool zooms the viewer (the viewer camera); this goes back to the margin
        self.reset_zoom_btn = QtWidgets.QPushButton(u"ズームを戻す")
        self.reset_zoom_btn.setToolTip(u"2D パン/ズーム（\\ キー＋ドラッグ）で変えた見え方を、余白の大きさに戻します")
        self.reset_zoom_btn.clicked.connect(self._reset_zoom)
        # how dark outside the frame (the user, 2026-10-27): 0 = as the layers are, 100 = black
        self.shade_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.shade_slider.setRange(0, 100)
        self.shade_slider.setSingleStep(5)
        self.shade_slider.setPageStep(10)
        self.shade_slider.setFixedWidth(90)
        self.shade_slider.setValue(int(round(layer_stack.shade() * 100)))
        self.shade_label = QtWidgets.QLabel()
        self.shade_label.setMinimumWidth(32)
        for widget in (self.shade_slider, self.shade_label):
            widget.setToolTip(u"枠の外側を暗くする濃さ（0% = 暗くしない、100% = 黒）。ビューアーだけの表示で、"
                              u"レンダーと Playblast には影響しません")
        self.shade_slider.valueChanged.connect(self._set_shade)
        self._show_shade(self.shade_slider.value())
        # Phase 3 from here too: the layer map is not always open (the user, 2026-10-25)
        self.motion = motion_transfer.MotionTransfer(self, self.say)
        motion_btn = QtWidgets.QPushButton(u"すべてのアニメーションを転送…")
        motion_btn.setToolTip(u"つないだすべての AE のレイヤーの動きを、範囲の各フレームのキーとしてそれぞれの専用カメラに打ちます"
                              u"（範囲の指定と確認は 1 回。Ctrl+Z 1 回で全部戻ります）。1 つのレイヤーだけなら、下の一覧で右クリック")
        motion_btn.clicked.connect(self.motion.all)
        from .layer_map_view import make_live_check
        self.live_check = make_live_check()                 # D-41, shared with the layer map and AE
        self.live_check.toggled.connect(self._toggle_live)
        bar = QtWidgets.QHBoxLayout()
        bar.addWidget(self.camera_label, 1)
        bar.addWidget(self.live_check)
        bar.addWidget(motion_btn)
        bar.addWidget(QtWidgets.QLabel(u"余白"))
        bar.addWidget(self.margin_combo)
        bar.addWidget(self.reset_zoom_btn)
        bar.addWidget(QtWidgets.QLabel(u"枠の外"))
        bar.addWidget(self.shade_slider)
        bar.addWidget(self.shade_label)
        bar.addWidget(self.frame_btn)
        bar.addWidget(self.custom_btn)
        bar.addWidget(self.custom_w)
        bar.addWidget(QtWidgets.QLabel(u"×"))
        bar.addWidget(self.custom_h)
        bar.addWidget(map_btn)

        # Maya finds the layout by the objectNames of it and its parents: every one needs a name
        # ("setParent: Object 'SyncBridgeViewer|||' not found" without them, the user, 2026-10-25)
        self.view_host = QtWidgets.QWidget()
        self.view_host.setObjectName("SyncBridgeViewerHost")
        self.view_layout = QtWidgets.QVBoxLayout(self.view_host)
        self.view_layout.setObjectName("SyncBridgeViewerLayout")
        self.view_layout.setContentsMargins(0, 0, 0, 0)
        self.layers = LayerStackList()
        self.layers.order_changed.connect(self._on_order)
        self.layers.visible_changed.connect(self._on_visible)
        self.layers.motion_requested.connect(self.motion.layer)
        self.layers.editing_requested.connect(self.set_editing)
        self._editing: Optional[str] = None               # the editing Maya layer's id (D-44)
        self._view_widget = None
        self._press = None                                # a left press that may become a click on a layer
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        split.setObjectName("SyncBridgeViewerSplit")
        split.addWidget(self.view_host)
        split.addWidget(self.layers)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setObjectName("SyncBridgeViewerMain")
        lay.addLayout(bar)
        lay.addWidget(split, 1)
        lay.addWidget(self.status)

        # Reading the scene again is deferred and coalesced: the list must not be rebuilt inside the signal
        # of one of its own rows (the eye's itemChanged), and a burst of toggles needs one refresh only.
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._refresh_now)
        # the selection, made anywhere, is followed once Maya and the viewer's own click are done (9.5)
        self._sel_timer = QtCore.QTimer(self)
        self._sel_timer.setSingleShot(True)
        self._sel_timer.setInterval(30)
        self._sel_timer.timeout.connect(self._follow_selection)
        self._sel_seen = None                             # the selection followed last
        self._noted = False                               # the status line says the selection does not match

        self._make_panel()
        service.add_listener(self.on_event)
        viewer_camera.gate_listeners.append(self._on_gate)
        self._jobs = [cmds.scriptJob(event=[name, self.refresh]) for name in
                      ("Undo", "Redo", "SceneOpened", "NewSceneOpened")]
        self._jobs.append(cmds.scriptJob(event=["SelectionChanged", self._sel_timer.start]))
        self.refresh()
        self._show_live()

    # -- the embedded Maya view ----------------------------------------------------------------------------
    def _make_panel(self):
        layout_name = omui.MQtUtil.fullName(int(getCppPointer(self.view_layout)[0]))
        if not layout_name or "||" in layout_name or layout_name.endswith("|"):
            raise RuntimeError(u"ビューの置き場所の名前が取れませんでした（%s）。" % layout_name)
        cmds.setParent(layout_name)
        self._pane = cmds.paneLayout(configuration="single")
        self.panel = cmds.modelPanel(label=u"SyncBridge Viewer", parent=self._pane, menuBarVisible=True)
        ptr = omui.MQtUtil.findControl(self._pane)
        self.view_layout.addWidget(wrapInstance(int(ptr), QtWidgets.QWidget))
        layer_stack.ensure_plugin()
        cmds.modelEditor(self.panel, e=True, rendererName="vp2Renderer",
                         rendererOverrideName=layer_stack.OVERRIDE_NAME, displayAppearance="smoothShaded",
                         grid=False)
        self._watch_clicks()

    def _watch_clicks(self):
        """Clicks on another layer's mesh make it the editing layer (D-44, H-MY-40)."""
        try:
            import maya.api.OpenMayaUI as omui2
            view = omui2.M3dView.getM3dViewFromModelPanel(self.panel)
            self._view_widget = wrapInstance(int(view.widget()), QtWidgets.QWidget)
            self._view_widget.installEventFilter(self)
        except Exception as exc:                 # the viewer works without it (choose layers in the list)
            self._view_widget = None
            print("SyncBridge: viewer clicks are not watched: %s" % exc)

    def eventFilter(self, obj, event):
        """Maya always gets the mouse; a click (press and release in place) on another layer's mesh is
        applied after Maya's own selection. Taking the press made a drag on the manipulator a click on the
        layer under it whenever the press was not near the selection's pivot (the user, 2026-10-27)."""
        if obj is not self._view_widget:
            return False
        kind = event.type()
        if kind == QtCore.QEvent.Type.Resize:
            self._set_view_aspect()
        elif kind == QtCore.QEvent.Type.MouseButtonPress:
            self._press = None
            mode = _click_mode(event.modifiers())
            if event.button() == QtCore.Qt.MouseButton.LeftButton and mode:
                self._press = (event.pos(), cmds.ls(selection=True, long=True) or [], mode)
        elif kind == QtCore.QEvent.Type.MouseButtonRelease and self._press is not None:
            press, self._press = self._press, None
            pos = event.pos()
            if (pos - press[0]).manhattanLength() <= CLICK_SLOP_PX:
                QtCore.QTimer.singleShot(0, lambda: self._click(pos, press[1], press[2]))   # after Maya's release
            else:                                # a marquee (or a manipulator drag: the selection stays)
                QtCore.QTimer.singleShot(0, lambda: self._dragged(press[1], press[2]))
        return False

    def _keep_to_drawn(self, store: dict, before: list, mode: str) -> None:
        """Maya selects through the viewer camera from the whole scene, also what the viewer does not draw:
        another layer's objects where the viewer camera would see them, objects of no layer, a hidden layer
        (H-MY-44). What Maya selected, or took out with Shift / Ctrl, that is not the editing layer's is put
        back as it was (P-1, 2026-10-28; isolating the panel would also hide the other layers). Outside the
        undo queue: Maya's own selection stays the one undo of the click."""
        layer = core_lm.maya_layer(store, self._editing)
        if layer is None:
            return
        roots = [p for p in (layer_mapping.node_by_uuid(o.get("uuid")) for o in layer.get("objects") or []) if p]
        after = cmds.ls(selection=True, long=True) or []
        added = [n for n in after if n not in before and not core_lm.related(n, roots)]
        removed = []
        if mode in ("toggle", "deselect"):              # a replace takes out the rest on purpose
            removed = [n for n in before if n not in after and cmds.objExists(n) and not core_lm.related(n, roots)]
        if added or removed:
            with viewer_camera._no_undo():
                if added:
                    cmds.select(added, deselect=True)
                if removed:
                    cmds.select(removed, add=True)

    def _dragged(self, before: list, mode: str) -> None:
        try:
            if (cmds.ls(selection=True, long=True) or []) != before:
                self._keep_to_drawn(layer_mapping.store(), before, mode)
        except Exception as exc:                 # never break the viewer
            print("SyncBridge: viewer marquee: %s" % exc)

    def _click(self, pos, selected_before: list, mode: str) -> None:
        """A click on another layer's mesh makes that layer the editing one and selects the mesh, as Maya's
        click with the same keys would: replace, Shift toggles, Ctrl+Shift adds (P-4, 2026-10-28)."""
        try:
            from . import viewer_pick
            widget = self._view_widget
            w, h = float(widget.width()), float(widget.height())
            if (mode == "replace" and selected_before
                    and (cmds.ls(selection=True, long=True) or []) == selected_before
                    and not viewer_pick.on_selection(pos.x(), pos.y(), w, h)):
                return                           # a click on the manipulator (Maya kept the selection)
            store = layer_mapping.store()
            self._keep_to_drawn(store, selected_before, mode)
            if mode == "deselect":
                return
            hit = viewer_pick.pick(store, pos.x(), pos.y(), w, h)
            if hit is None or hit["layer"] == self._editing:
                return                           # Maya picked in the editing layer's picture
            if mode == "toggle" and hit["node"] in selected_before:
                # Maya toggled where the viewer camera sees, not this mesh: take it out, keep the editing layer
                cmds.select(hit["node"], deselect=True)
                return
            self.set_editing(hit["layer"])
            if mode == "replace":
                cmds.select(hit["node"], replace=True)
            else:
                cmds.select(hit["node"], add=True)
        except Exception as exc:                 # never break the viewer
            print("SyncBridge: viewer click: %s" % exc)

    def _look_through(self, store: dict) -> Optional[str]:
        """The original camera of the top layer, shown or hidden (the frame and the HUD follow it)."""
        return layer_stack.view_camera(store)

    # -- the editing layer and the 2D pan / zoom (D-44) ---------------------------------------------------
    def set_editing(self, layer_id: Optional[str]):
        """Edit this layer in the viewer: the panel looks through the viewer camera that follows it."""
        store = layer_mapping.store()
        layer = core_lm.maya_layer(store, layer_id)
        dedicated = layer_mapping.node_by_uuid(core_lm.driven_camera(layer)["camera_uuid"]) if layer else None
        if layer is not None and not dedicated:
            self.say(u"Maya レイヤー「%s」にはカメラがないので、編集中にできません（レイヤーマップでカメラを設定してください）。"
                     % layer["name"], error=True)
            return
        if layer is not None and not layer.get("visible", True):
            # a hidden layer is not drawn: Maya would select and move its unseen objects (P-5, 2026-10-28)
            self.say(u"「%s」は非表示なので、編集中にできません。左のチェックで表示してから選んでください。" % layer["name"],
                     error=True)
            return
        self._editing = layer_id if dedicated else None
        # now, not on the deferred refresh: the view must not be drawn between the viewer camera moving and
        # the layer stack / the panel following it (it flickered, the user, 2026-10-27)
        self._sync_view(store)
        if layer is not None:
            self.say(u"「%s」を編集中にしました。ビューでの選択・移動は、このレイヤーの見え方どおりになります。" % layer["name"])
            self._sel_seen = self._selection()            # the viewer camera's own selection changes are not followed
            self._note_selection(store)
        self.refresh()

    # -- the selection (9.5 of docs/VIEWER_CAMERA_SELECTION_AUDIT.md) ---------------------------------------
    @staticmethod
    def _selection() -> list:
        return [n for n in cmds.ls(selection=True, long=True) or [] if not viewer_camera._is_viewer(n)]

    @staticmethod
    def _layer_roots(store: dict) -> list:
        """[(layer id, [object paths])] of the shown layers, top first."""
        out = []
        for item in reversed(core_lm.stack(store)):
            layer = core_lm.maya_layer(store, item["id"])
            out.append((item["id"], [p for p in (layer_mapping.node_by_uuid(o.get("uuid"))
                                                 for o in layer.get("objects") or []) if p]))
        return out

    def _follow_selection(self):
        """A new selection all in one shown layer, made anywhere (the Outliner, another view, an undo), makes
        that layer the editing one; a mixed one, one with objects the viewer does not draw, or none keeps it
        (core selection_layers). Only a change of the selection: putting it back after the viewer camera
        moved (P-11) must not undo a layer chosen in the list."""
        try:
            selection = self._selection()
            changed, self._sel_seen = selection != self._sel_seen, selection
            store = layer_mapping.store()
            found = core_lm.selection_layers(self._layer_roots(store), selection, self._editing)
            if changed and found["target"] and found["target"] != self._editing:
                self.set_editing(found["target"])
                return
            self._note_selection(store, found)
        except Exception as exc:                 # never break Maya's selection
            print("SyncBridge: viewer selection: %s" % exc)

    def _note_selection(self, store: dict, found: Optional[dict] = None):
        """Say when the manipulator, drawn as the editing layer sees, does not match the selection."""
        if self._editing is None:
            return
        if found is None:
            found = core_lm.selection_layers(self._layer_roots(store), self._selection(), self._editing)
        names = dict((layer["id"], layer["name"]) for layer in store["maya_layers"])
        editing = names.get(self._editing, "?")
        text = None
        if found["unknown"]:
            shown = [core_lm.short_name(n) for n in found["unknown"][:3]]
            more = len(found["unknown"]) - len(shown)
            text = (u"選択の %s%s は、ビューアーに描かれていません（どのレイヤーにもないか、非表示のレイヤーのもの）。"
                    u"マニピュレーターだけが「%s」の見え方で出ます。"
                    % (u"、".join(shown), u" ほか %d 個" % more if more > 0 else u"", editing))
        else:
            others = [names.get(lid, "?") for lid in found["layers"] if lid != self._editing]
            if others:
                text = (u"選択に「%s」のレイヤーのものが入っています。マニピュレーターは編集中の「%s」の見え方なので、"
                        u"そのオブジェクトの見た目の位置・動きとは合いません。" % (u"」「".join(others), editing))
        if text:
            self.say(text, warn=True)
            self._noted = True
        elif self._noted:
            self.say(u"")
            self._noted = False

    def _apply_editing(self, store: dict) -> Optional[str]:
        """Make / move / remove the viewer camera for the editing layer; returns the camera to look through.
        Only a shown layer is edited: a hidden one goes to the top shown layer (P-5, 2026-10-28)."""
        ids = [item["id"] for item in reversed(core_lm.stack(store))]               # shown and drawable, top first
        if self._editing not in ids:
            self._editing = ids[0] if ids else None
        self.layers.set_editing(self._editing)
        if self._editing is None:
            viewer_camera.remove()
            return None
        layer = core_lm.maya_layer(store, self._editing)
        dedicated = layer_mapping.node_by_uuid(core_lm.driven_camera(layer)["camera_uuid"])
        before = self._current_view(dedicated)
        shape = viewer_camera.ensure(dedicated, initial_zoom=layer_stack.margin())
        self._set_view_aspect(shape)
        if before is not None:
            self._keep_view(shape, dedicated, before)
        return cmds.listRelatives(shape, parent=True, fullPath=True)[0]

    def _view_size(self):
        widget = self._view_widget
        if widget is None or widget.width() < 2 or widget.height() < 2:
            return None
        return float(widget.width()), float(widget.height())

    def _set_view_aspect(self, shape=None):
        """The steady view's pan depends on the view's width / height (D-48)."""
        size = self._view_size()
        if size is not None:
            try:
                viewer_camera.set_view_aspect(size[0] / size[1], shape)
            except Exception as exc:                 # never break the view's resize
                print("SyncBridge: the viewer's aspect was not set: %s" % exc)

    def _current_view(self, dedicated: str):
        """The view (core view_affine) while another layer is edited, to keep it when this one becomes the
        editing layer; None when nothing changes."""
        from . import layer_camera, pixel_mapping
        from syncbridge.core import stack_view as core_view
        old, size = viewer_camera.current(), self._view_size()
        if not old or size is None:
            return None
        followed = viewer_camera.followed(old)
        if not followed or followed == layer_camera._shape(dedicated):
            return None
        try:
            return core_view.view_affine(pixel_mapping.camera_data(followed), pixel_mapping.camera_data(old), *size)
        except ValueError:                        # an orthographic camera: the numbers are kept as they are
            return None

    def _keep_view(self, shape: str, dedicated: str, view):
        """The pan / zoom that shows the same view through the new editing camera (core match_view)."""
        from . import layer_camera, pixel_mapping
        from syncbridge.core import stack_view as core_view
        try:
            # the steady view (D-48): the pan / zoom is a view of the camera without its film translate,
            # roll and post-scale
            camera = core_view.unmoved(pixel_mapping.camera_data(layer_camera._shape(dedicated)))
            hpan, vpan, zoom = core_view.match_view(view, camera, *self._view_size())
        except (ValueError, TypeError, ZeroDivisionError):
            return
        viewer_camera.set_view(shape, hpan, vpan, zoom)

    def _set_margin(self, index: int):
        layer_stack.set_margin(self.margin_combo.itemData(index))
        self._reset_zoom()

    def _reset_zoom(self):
        shape = viewer_camera.current()
        if shape:
            viewer_camera.set_view(shape, 0.0, 0.0, layer_stack.margin())

    # -- data ----------------------------------------------------------------------------------------------
    def refresh(self, *_args):
        self._timer.start()

    def _refresh_now(self):
        try:
            store = layer_mapping.store()
        except Exception as exc:
            self.say(u"レイヤーマップを読めませんでした: %s" % exc, error=True)
            return
        self.layers.set_data(store)
        self._repair_cameras(store)
        self._sync_view(store)

    def _sync_view(self, store: dict):
        """The viewer camera, the layer stack and the panel's camera, in one go."""
        try:
            viewer = self._apply_editing(store)              # before publish: it hands the editing layer on
        except Exception as exc:
            viewer = None
            self.say(u"編集中のレイヤーのビューを作れませんでした: %s" % exc, error=True)
        try:
            stack = layer_stack.publish()
        except Exception as exc:
            self.say(u"重ねて表示できませんでした: %s" % exc, error=True)
            return
        camera = viewer or self._look_through(store)
        if camera and self.panel:
            # by node, not path: the viewer camera keeps its node when it moves to another layer, and setting
            # the same camera again right after the move crashed Maya 2024 (2026-10-27)
            now = cmds.modelEditor(self.panel, q=True, camera=True)
            if not now or not cmds.objExists(now) or _uuid(now) != _uuid(camera):
                cmds.modelEditor(self.panel, e=True, camera=camera)
        editing = core_lm.maya_layer(store, self._editing)
        self.camera_label.setText(u"編集中: %s（重ねて表示: %d レイヤー）" % (editing["name"], len(stack)) if editing
                                  else u"重ねて表示: %d レイヤー" % len(stack))

    def _repair_cameras(self, store: dict):
        """Dedicated cameras made by an earlier version: link what they lack from the original and put
        the overscan back to 1.0 (other overscans slide the layers off the frame, D-34). One undo."""
        from . import layer_camera
        fixed = []
        for layer in store["maya_layers"]:
            own = layer_mapping.node_by_uuid(layer.get("layer_camera_uuid"))
            if own and layer_camera.needs_repair(own):
                fixed.append(own)
        if not fixed:
            return
        cmds.undoInfo(openChunk=True, chunkName="SyncBridge repair dedicated cameras")
        try:
            for own in fixed:
                layer_camera.repair(own)
        finally:
            cmds.undoInfo(closeChunk=True)
        self.say(u"専用カメラ %s の Overscan を 1.0 にしました（1.0 以外だとレイヤーが枠からずれるため）。"
                 % u"、".join(_label(c) for c in fixed))

    def _set_custom(self, *_args):
        shown, w, h = self.custom_btn.isChecked(), self.custom_w.value(), self.custom_h.value()
        if (layer_stack.custom_frame() or None) == ((w, h) if shown else None):
            return                                   # editingFinished also comes on losing focus
        try:
            layer_stack.set_custom_frame(shown, w, h)
        except Exception as exc:
            self.say(u"任意の枠を切り替えられませんでした: %s" % exc, error=True)
            return
        self.say(u"%d×%d の任意の枠を出しました。" % (w, h) if shown else u"任意の枠を消しました。")

    def _on_gate(self, message: str):
        self.say(message, error=True)

    def _toggle_frame(self, shown: bool):
        try:
            layer_stack.set_frame_shown(shown)
        except Exception as exc:
            self.say(u"解像度の枠を切り替えられませんでした: %s" % exc, error=True)
            return
        if shown:
            self.say(u"Maya のレンダー設定の解像度（%d×%d）の枠を出しました。"
                     % (cmds.getAttr("defaultResolution.width"), cmds.getAttr("defaultResolution.height")))
        else:
            self.say(u"解像度の枠を消しました。")

    def _on_order(self, layer_ids):
        self._do(lambda: layer_mapping.reorder_layers(layer_ids), u"重なり順を変えました（Ctrl+Z で戻せます）。")

    def _on_visible(self, layer_id, visible):
        self._do(lambda: layer_mapping.set_layer_visible(layer_id, visible),
                 u"表示を%sにしました。" % (u"オン" if visible else u"オフ"))

    def _do(self, action, done):
        try:
            action()
        except Exception as exc:
            self.say(u"できませんでした: %s" % exc, error=True)
        else:
            self.say(done)
            service.announce("layer_map")
        self.refresh()

    def say(self, text: str, error: bool = False, warn: bool = False):
        """error: also in the Script Editor; warn: the same colour only (said on every selection change)."""
        self._noted = False                               # _note_selection sets it after its own message
        self.status.setStyleSheet("color: #e08a40;" if error or warn else "")
        self.status.setText(text)
        if error:
            print("SyncBridge: %s" % text)

    def on_event(self, event, payload):
        if event in ("layer_map", "pixelmap"):
            self.refresh()
        elif event in ("live_sync", "connected", "disconnected"):
            self._show_live()
        elif event == "live_applied":
            self.say(payload["text"], error=payload.get("error", False))

    def _show_live(self):
        from .layer_map_view import show_live
        live = service.live_sync_state()
        show_live(self.live_check, live["enabled"], service.is_connected(), len(live.get("layers") or []))

    def _toggle_live(self, enabled: bool):
        try:
            service.set_live_sync(enabled)
        except Exception as exc:
            self.say(u"リアルタイム同期を切り替えられませんでした: %s（SyncBridge のパネルで Connect してください）" % exc,
                     error=True)
        self._show_live()

    def _show_shade(self, value: int):
        self.shade_label.setText(u"%d%%" % value)

    def _set_shade(self, value: int):
        self._show_shade(value)
        try:
            layer_stack.set_shade(value / 100.0)
        except Exception as exc:
            self.say(u"枠の外の濃さを変えられませんでした: %s" % exc, error=True)

    def _open_layer_map(self):
        from . import layer_map_window
        layer_map_window.show()

    def closeEvent(self, event):
        self._timer.stop()
        self._sel_timer.stop()
        service.remove_listener(self.on_event)
        if self._on_gate in viewer_camera.gate_listeners:
            viewer_camera.gate_listeners.remove(self._on_gate)
        for job in self._jobs:
            if job is not None and cmds.scriptJob(exists=job):      # None in mayapy (no UI)
                cmds.scriptJob(kill=job, force=True)
        self._jobs = []
        if self._view_widget is not None:
            try:
                self._view_widget.removeEventFilter(self)
            except RuntimeError:                              # the panel's widget is gone already
                pass
            self._view_widget = None
        if self.panel and cmds.modelPanel(self.panel, exists=True):
            cmds.deleteUI(self.panel, panel=True)
        self.panel = None
        try:                                                  # the viewer camera is the viewer's only (D-44)
            viewer_camera.remove()
            layer_stack.publish()
        except Exception as exc:
            print("SyncBridge: viewer camera: %s" % exc)
        super().closeEvent(event)


def show() -> ViewerWindow:
    global _window
    if _window is not None:
        try:
            _window.close()
            _window.deleteLater()
        except RuntimeError:   # already deleted by Qt
            pass
    _window = ViewerWindow(_maya_main_window())
    _window.show()
    return _window
