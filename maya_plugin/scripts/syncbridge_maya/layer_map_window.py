"""The layer map window (D-28): the node editor (layer_map_view) on the scene's layer map.

    import syncbridge_maya.layer_map_window as lmw
    lmw.show()

Each change is one undo chunk (layer_mapping); the window reads the store again after undo / redo,
a scene change and a send from AE, so it always shows what is in the scene.
"""
from __future__ import annotations

from typing import Optional

from maya import OpenMayaUI as omui
from maya import cmds

try:
    from PySide6 import QtCore, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtCore, QtWidgets
    from shiboken2 import wrapInstance

from syncbridge.core import layer_mapping as core_lm

from . import layer_mapping, service
from .layer_map_view import LayerMapEditor

WINDOW_NAME = "SyncBridgeLayerMap"
_window = None
_last_ae: Optional[dict] = None         # the AE layers read last (kept while Maya runs)


def _with_warnings(text: str, warnings) -> str:
    return text + "".join(u"\n注意: %s" % w for w in warnings or [])


def _maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr is not None else None


class LayerMapWindow(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(WINDOW_NAME)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowType.Window)
        self.setWindowTitle(u"SyncBridge レイヤーマップ")
        self.resize(1100, 620)
        self.editor = LayerMapEditor()
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.editor, 1)
        layout.addWidget(self.status)

        e = self.editor
        e.set_new_method(layer_mapping.defaults()["method"])
        e.new_method_changed.connect(lambda method: layer_mapping.set_defaults(method=method))
        e.reload_requested.connect(self.load_ae_layers)
        e.add_layer_requested.connect(lambda: self._do(
            lambda: layer_mapping.add_layer(),
            lambda result: _with_warnings(u"Maya レイヤー「%s」を追加しました%s。" % (
                result[0]["name"],
                u"（専用カメラ %s を %s の下に作りました）" % (core_lm.short_name(result[0]["layer_camera"]),
                                                             core_lm.short_name(result[0]["camera"]))
                if result[0].get("layer_camera") else
                u"。カメラとオブジェクトを選んで、右の欄から設定してください"), result[1])))
        e.link_requested.connect(lambda ae, layer_id: self._do(
            lambda: layer_mapping.connect(ae, layer_id),
            lambda m: u"つなぎました: %s" % core_lm.describe(m)))
        e.unlink_requested.connect(lambda mapping_id: self._do(
            lambda: layer_mapping.disconnect(mapping_id), u"接続を外しました（Ctrl+Z で戻せます）。"))
        e.method_requested.connect(lambda mapping_id, method: self._do(
            lambda: layer_mapping.change_method(mapping_id, method),
            lambda m: u"方式を変えました: %s" % core_lm.describe(m)))
        e.mode_requested.connect(lambda mapping_id, mode: self._do(
            lambda: layer_mapping.change_mode(mapping_id, mode),
            lambda m: u"モードを変えました: %s" % core_lm.describe(m)))
        e.reset_reference_requested.connect(lambda mapping_id: self._do(
            lambda: layer_mapping.reset_reference(mapping_id),
            u"基準を消しました。Maya と AE の見え方を合わせてから AE で送ると、新しい基準になります。"))
        e.rename_layer_requested.connect(lambda layer_id, name: self._do(
            lambda: layer_mapping.rename_layer(layer_id, name), u"名前を「%s」にしました。" % name))
        e.camera_requested.connect(lambda layer_id: self._do(
            lambda: layer_mapping.set_camera_from_selection(layer_id),
            lambda result: _with_warnings(
                u"カメラを %s にしました（専用カメラ %s をその下へ。つながっている接続は次の送信で基準を取り直します）。"
                % (core_lm.short_name(result[0]["camera"]), core_lm.short_name(result[0]["layer_camera"])),
                result[1])))
        e.add_objects_requested.connect(lambda layer_id: self._do(
            lambda: layer_mapping.add_selected_objects(layer_id), lambda n: u"オブジェクトを %d 個追加しました。" % n))
        e.remove_objects_requested.connect(lambda layer_id, uuids: self._do(
            lambda: layer_mapping.remove_objects(layer_id, uuids), u"オブジェクトを外しました。"))
        e.select_objects_requested.connect(self.select_layer)
        e.remove_layer_requested.connect(self.remove_layer)

        service.add_listener(self.on_event)
        self._jobs = [cmds.scriptJob(event=[name, self.refresh]) for name in
                      ("Undo", "Redo", "SceneOpened", "NewSceneOpened")]
        self.refresh()
        if _last_ae is None and service.is_connected():
            self.load_ae_layers()

    # -- actions ----------------------------------------------------------------------------------------
    def _do(self, action, done):
        """Run one change; `done` is the message (or makes it from the result)."""
        try:
            result = action()
        except Exception as exc:
            self.say(u"できませんでした: %s" % exc, error=True)
        else:
            self.say(done(result) if callable(done) else done)
            service.announce("layer_map")
        self.refresh()

    def say(self, text: str, error: bool = False):
        self.status.setStyleSheet("color: #e08a40;" if error else "")
        self.status.setText(text)
        print("SyncBridge: %s" % text)

    def refresh(self, *_args):
        try:
            data = layer_mapping.store()
        except Exception as exc:
            self.say(u"レイヤーマップを読めませんでした: %s" % exc, error=True)
            data = core_lm.empty_store()
        self.editor.set_data(_last_ae, data)

    def load_ae_layers(self):
        if not service.is_connected():
            self.say(u"SyncBridge のサーバーに接続していません。SyncBridge のパネルで Connect を押してください。", error=True)
            return
        self.say(u"AE のレイヤーを読み込んでいます…")

        def done(reply):
            global _last_ae
            if reply["kind"] == "error":
                self.say(reply["data"].get("message") or u"AE のレイヤーを読み込めませんでした。", error=True)
                return
            _last_ae = {"comp": reply["data"]["comp"], "layers": reply["data"]["layers"]}
            self.say(u"AE のコンプ「%s」のレイヤーを %d 個読み込みました。" % (
                _last_ae["comp"].get("name"), len(_last_ae["layers"])))
            self.refresh()
        try:
            service.request_ae_layers(done)
        except Exception as exc:
            self.say(u"AE のレイヤーを読み込めませんでした: %s" % exc, error=True)

    def select_layer(self, layer_id: str):
        try:
            missing = layer_mapping.select_layer(layer_id)
        except Exception as exc:
            self.say(u"選択できませんでした: %s" % exc, error=True)
            return
        self.say(u"シーンにないもの: %s" % u"、".join(missing) if missing else u"カメラとオブジェクトを選択しました。",
                 error=bool(missing))

    def remove_layer(self, layer_id: str):
        layer = core_lm.maya_layer(self.editor.store, layer_id)
        if layer is None:
            return
        links = len(core_lm.links_of(self.editor.store, layer_id))
        text = u"Maya レイヤー「%s」を削除しますか？" % layer["name"]
        if links:
            text += u"\nつながっている接続 %d 本も外れます。" % links
        if layer.get("layer_camera"):
            text += u"\n専用カメラ %s（SyncBridge が付けた動きごと）も削除します。" % core_lm.short_name(layer["layer_camera"])
        text += u"\n（元のカメラとオブジェクトはそのまま。Ctrl+Z で戻せます）"
        answer = QtWidgets.QMessageBox.question(self, "SyncBridge", text)
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._do(lambda: layer_mapping.remove_layer(layer_id),
                 u"Maya レイヤー「%s」を削除しました。" % layer["name"])

    def on_event(self, event, payload):
        if event == "pixelmap":                # a send from AE may have made or changed a link
            self.refresh()

    def closeEvent(self, event):
        service.remove_listener(self.on_event)
        for job in self._jobs:
            if job is not None and cmds.scriptJob(exists=job):      # None in mayapy (no UI)
                cmds.scriptJob(kill=job, force=True)
        self._jobs = []
        super().closeEvent(event)


def show() -> LayerMapWindow:
    global _window
    if _window is not None:
        try:
            _window.close()
            _window.deleteLater()
        except RuntimeError:   # already deleted by Qt
            pass
    _window = LayerMapWindow(_maya_main_window())
    _window.show()
    return _window
