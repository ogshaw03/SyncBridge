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


def _camera_label(path) -> str:
    from .motion import camera_label
    return camera_label(path)


def _with_warnings(text: str, warnings) -> str:
    return text + "".join(u"\n注意: %s" % w for w in warnings or [])


class MotionDialog(QtWidgets.QDialog):
    """The Maya frame range to key and the Origin frame (Maya frame of AE comp time 0)."""

    def __init__(self, text: str, start: float, end: float, origin: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle(u"SyncBridge - アニメーションを転送")
        self.setMinimumWidth(460)
        self.start, self.end, self.origin = (QtWidgets.QDoubleSpinBox() for _ in range(3))
        for box, value in ((self.start, start), (self.end, end), (self.origin, origin)):
            box.setRange(-1e6, 1e6)
            box.setDecimals(0)
            box.setValue(value)
        form = QtWidgets.QFormLayout()
        form.addRow(u"開始フレーム", self.start)
        form.addRow(u"終了フレーム", self.end)
        form.addRow(u"Origin frame", self.origin)
        text = QtWidgets.QLabel(text + u"\nOrigin frame は AE のコンプの 0 秒にあたる Maya のフレームです（パネルと同じ値）。")
        text.setWordWrap(True)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok |
                                             QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(text)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def _accept(self):
        if self.end.value() < self.start.value():
            QtWidgets.QMessageBox.warning(self, "SyncBridge", u"終了フレームは開始フレームより後にしてください。")
            return
        self.accept()

    def values(self):
        return self.start.value(), self.end.value(), self.origin.value()


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
        e.motion_requested.connect(self.transfer_motion)
        e.motion_all_requested.connect(self.transfer_all_motion)
        e.view_layer_requested.connect(self.view_layer)
        e.view_all_requested.connect(self.view_all)
        e.viewer_requested.connect(self._open_viewer)
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
        self._publish_stack()

    def _publish_stack(self):
        """Keep the layer stack view (D-32) in step with the layer map."""
        from . import layer_stack
        try:
            if layer_stack.enabled_panels():
                layer_stack.publish()
        except Exception as exc:  # the view is a convenience: never break the window
            print("SyncBridge: layer stack: %s" % exc)

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

    # -- Phase 3 (D-30) ----------------------------------------------------------------------------------
    def transfer_motion(self, mapping_id: str):
        """One link (the selected wire)."""
        link = next((m for m in layer_mapping.stored() if m["id"] == mapping_id), None)
        if link is not None:
            self._transfer([link], [], u"AE のレイヤー「%s」の動きを、範囲の各フレームのキーとしてカメラ %s に打ちます。"
                           % (link["ae"].get("layer"), _camera_label(link["maya"].get("camera"))))

    def transfer_all_motion(self):
        """Every link: one range, AE asked link by link, one confirmation, one undo."""
        from . import motion
        links, skipped = motion.transferable(layer_mapping.store())
        if not links:
            self.say(u"転送できる接続がありません。" + u" ".join(skipped), error=True)
            return
        text = u"%d 本の接続の AE の動きを、範囲の各フレームのキーとしてそれぞれのカメラに打ちます。" % len(links)
        if skipped:
            text += u"（%d 本は打ちません: 確認の画面に理由が出ます）" % len(skipped)
        self._transfer(links, skipped, text)

    def _transfer(self, links, skipped, text):
        """Range dialog -> ask AE for each link's layer at every frame -> solve -> confirm -> keys."""
        from . import motion
        if not service.is_connected():
            self.say(u"SyncBridge のサーバーに接続していません。SyncBridge のパネルで Connect を押してください。", error=True)
            return
        dialog = MotionDialog(text, cmds.playbackOptions(q=True, minTime=True),
                              cmds.playbackOptions(q=True, maxTime=True), service.time_sync_origin(), self)
        run = getattr(dialog, "exec", None) or dialog.exec_       # PySide6 / PySide2
        if not run():
            return
        start, end, origin = dialog.values()
        skipped = list(skipped)
        queries = []
        for link in links:
            try:
                queries.append((link, motion.query(link["id"], start, end, origin)))
            except Exception as exc:
                skipped.append(u"%s: %s" % (link["ae"].get("layer"), exc))
        if not queries:
            self.say(u"アニメーションを転送できません: " + u" ".join(skipped), error=True)
            return
        plans = []

        def ask(i):
            if i == len(queries):
                self._finish_transfer(plans, skipped, len(links) == 1)
                return
            link, q = queries[i]
            self.say(u"AE から「%s」の動きを読み込んでいます…（%d / %d）" % (link["ae"].get("layer"), i + 1, len(queries)))

            def done(reply):
                name = link["ae"].get("layer")
                if reply["kind"] == "error":
                    skipped.append(u"%s: AE から読み込めませんでした（%s）" % (name, reply["data"].get("message")))
                else:
                    try:
                        plans.append(motion.plan(link["id"], q["frames"], reply["data"]))
                    except Exception as exc:
                        skipped.append(u"%s: %s" % (name, exc))
                ask(i + 1)
            try:
                service.request_ae_motion(q["request"], done)
            except Exception as exc:
                skipped.append(u"%s: %s" % (link["ae"].get("layer"), exc))
                ask(i + 1)
        ask(0)

    def _finish_transfer(self, plans, skipped, single):
        from . import motion
        if not plans:
            self.say(u"アニメーションを転送できませんでした（カメラは変えていません）: " + u" / ".join(skipped), error=True)
            return
        try:
            results = motion.apply_all(plans, parent=self, skipped=[] if single else skipped)
        except Exception as exc:
            self.say(u"アニメーションを転送できませんでした（カメラは変えていません）: %s" % exc, error=True)
            return
        if results[0]["status"] == "cancelled":
            self.say(u"アニメーションの転送はキャンセルしました（カメラは変えていません）。")
            return
        bad = [r for r in results if not r["readback"]["passed"]]
        lines = [u"%s → %s（%s、誤差 最大 %.3f px）" % (r["ae_layer"], _camera_label(r["camera"]), ", ".join(r["attrs"]),
                                                    r["max_error_px"]) for r in results]
        warnings = []
        for r in results:
            warnings += [w for w in r["warnings"] if w not in warnings]
        text = u"%g〜%g フレームのキーを打ちました（読み戻し %s）。元に戻すときは Ctrl+Z を 1 回。\n%s" % (
            results[0]["frames"][0], results[0]["frames"][1],
            u"一致" if not bad else u"不一致 %d 本" % len(bad), u"\n".join(lines))
        if skipped and not single:
            text += u"\n打たなかったもの: " + u" / ".join(skipped)
        self.say(_with_warnings(text, warnings), error=bool(bad))
        service.announce("layer_map")

    # -- D-31: show one layer in the view ------------------------------------------------------------------
    def view_layer(self, layer_id: str):
        from . import layer_view
        layer = core_lm.maya_layer(layer_mapping.store(), layer_id)
        if layer is None:
            return
        try:
            shown = layer_view.show_layer(layer)
        except Exception as exc:
            self.say(u"表示を切り替えられませんでした: %s" % exc, error=True)
            return
        self.editor.viewing = layer_id
        self.refresh()
        text = u"ビュー %s を %s にして、「%s」のオブジェクト %d 個だけを表示しました（「表示を戻す」で元に戻ります）。" % (
            shown["panel"], _camera_label(shown["camera"]), layer["name"], len(shown["shown"]))
        if shown["missing"]:
            text += u"\nシーンにないもの: %s" % u"、".join(shown["missing"])
        self.say(text, error=bool(shown["missing"]))

    def view_all(self):
        from . import layer_view
        try:
            panel = layer_view.show_all()
        except Exception as exc:
            self.say(u"表示を戻せませんでした: %s" % exc, error=True)
            return
        self.editor.viewing = None
        self.refresh()
        self.say(u"ビュー %s の表示を戻しました（カメラはそのままです）。" % panel)

    # -- D-33: the viewer ----------------------------------------------------------------------------------
    def _open_viewer(self):
        from . import viewer_window
        try:
            viewer_window.show()
        except Exception as exc:
            self.say(u"ビューアーを開けませんでした: %s" % exc, error=True)

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
