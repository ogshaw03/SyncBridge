"""The SyncBridge viewer (D-33): a Maya view that stacks the Maya layers like AE (the layer stack
render override, D-32) and, below it, an AE-like layer list to order and show / hide them.

    import syncbridge_maya.viewer_window as vw
    vw.show()

The view is a model panel made by this window (H-MY-34: a modelPanel can live in a Qt layout of our
window); it looks through the original camera of the top layer (for the gate and the HUD), while each
layer is drawn through its own dedicated camera. Order and visibility are saved in the scene (one undo
each). Nothing else in the scene changes.
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

from . import layer_mapping, layer_stack, motion_transfer, service
from .layer_stack_view import LayerStackList

WINDOW_NAME = "SyncBridgeViewer"
_window = None


def _label(camera_path: str) -> str:
    """Transform name of a camera shape path (what the Outliner shows)."""
    parts = camera_path.split("|")
    return parts[-2] if len(parts) > 1 and parts[-2] else parts[-1]


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
        self.frame_btn.setToolTip(u"AE の解像度の枠（パネルの「解像度の枠」と同じもの）を、このビューのカメラに出します。"
                                  u"Maya の解像度ゲートは Overscan を 1.3 にするので、ビューアーでは使いません")
        self.frame_btn.clicked.connect(self._show_frame)
        self.margin_combo = QtWidgets.QComboBox()
        for value, text in ((1.0, u"なし"), (1.1, u"10%"), (1.2, u"20%"), (1.3, u"30%")):
            self.margin_combo.addItem(text, value)
        self.margin_combo.setToolTip(u"枠を表示しているとき、ビューアーだけを少し縮めて枠のまわりを見せます"
                                     u"（カメラの値は変えません。普通のビューと Playblast には影響しません）")
        self.margin_combo.setCurrentIndex(max(0, self.margin_combo.findData(round(layer_stack.margin(), 2))))
        self.margin_combo.activated.connect(
            lambda i: layer_stack.set_margin(self.margin_combo.itemData(i)))
        # Phase 3 from here too: the layer map is not always open (the user, 2026-10-25)
        self.motion = motion_transfer.MotionTransfer(self, self.say)
        motion_btn = QtWidgets.QPushButton(u"すべてのアニメーションを転送…")
        motion_btn.setToolTip(u"つないだすべての AE のレイヤーの動きを、範囲の各フレームのキーとしてそれぞれの専用カメラに打ちます"
                              u"（範囲の指定と確認は 1 回。Ctrl+Z 1 回で全部戻ります）。1 つのレイヤーだけなら、下の一覧で右クリック")
        motion_btn.clicked.connect(self.motion.all)
        bar = QtWidgets.QHBoxLayout()
        bar.addWidget(self.camera_label, 1)
        bar.addWidget(motion_btn)
        bar.addWidget(QtWidgets.QLabel(u"余白"))
        bar.addWidget(self.margin_combo)
        bar.addWidget(self.frame_btn)
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

        self._make_panel()
        service.add_listener(self.on_event)
        self._jobs = [cmds.scriptJob(event=[name, self.refresh]) for name in
                      ("Undo", "Redo", "SceneOpened", "NewSceneOpened")]
        self.refresh()

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

    def _look_through(self, store: dict) -> Optional[str]:
        """The original camera of the top layer, shown or hidden (the frame and the HUD follow it)."""
        return layer_stack.view_camera(store)

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
        try:
            stack = layer_stack.publish()
        except Exception as exc:
            self.say(u"重ねて表示できませんでした: %s" % exc, error=True)
            return
        camera = self._look_through(store)
        if camera and self.panel:
            cmds.modelEditor(self.panel, e=True, camera=camera)
        self.camera_label.setText(u"カメラ: %s（重ねて表示: %d レイヤー）" % (
            core_lm.short_name(camera).replace("Shape", "") if camera else u"なし", len(stack)))

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

    def _show_frame(self):
        from . import comp_guide
        camera = self._look_through(layer_mapping.store())
        if not camera:
            self.say(u"枠を出すカメラがありません（重ねるレイヤーがありません）。", error=True)
            return
        try:
            width, height = comp_guide.last_size()
            comp_guide.show_size(width, height, camera=camera)
        except Exception as exc:
            self.say(u"枠を出せませんでした: %s" % exc, error=True)
            return
        self.say(u"%s に %d×%d の枠を出しました（大きさはパネルの「解像度の枠」か、AE から送ると変わります）。"
                 % (_label(camera), width, height))
        self.refresh()

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

    def say(self, text: str, error: bool = False):
        self.status.setStyleSheet("color: #e08a40;" if error else "")
        self.status.setText(text)
        if error:
            print("SyncBridge: %s" % text)

    def on_event(self, event, payload):
        if event in ("layer_map", "pixelmap"):
            self.refresh()

    def _open_layer_map(self):
        from . import layer_map_window
        layer_map_window.show()

    def closeEvent(self, event):
        self._timer.stop()
        service.remove_listener(self.on_event)
        for job in self._jobs:
            if job is not None and cmds.scriptJob(exists=job):      # None in mayapy (no UI)
                cmds.scriptJob(kill=job, force=True)
        self._jobs = []
        if self.panel and cmds.modelPanel(self.panel, exists=True):
            cmds.deleteUI(self.panel, panel=True)
        self.panel = None
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
