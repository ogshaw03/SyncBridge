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

from . import layer_map_view, layer_mapping, motion_transfer, service
from .layer_map_view import LayerMapEditor

WINDOW_NAME = "SyncBridgeLayerMap"
_window = None
_last_ae: Optional[dict] = None         # the AE layers read last (kept while Maya runs)


_camera_label = motion_transfer.camera_label
_with_warnings = motion_transfer.with_warnings


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
        e.set_new_mode(layer_mapping.defaults()["mode"])
        e.new_mode_changed.connect(lambda mode: layer_mapping.set_defaults(mode=mode))
        e.reload_requested.connect(self.load_ae_layers)
        e.add_selection_requested.connect(self.add_ae_selection)
        e.hide_ae_requested.connect(lambda key: self._do(
            lambda: layer_mapping.hide_ae_layer(key), u"AE のレイヤーをマップから外しました（Ctrl+Z で戻せます）。"))
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
        e.record_reference_requested.connect(self.record_reference)
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
        self.motion = motion_transfer.MotionTransfer(self, self.say)        # Phase 3 (D-30), shared with the viewer
        e.motion_requested.connect(self.motion.link)
        e.motion_all_requested.connect(self.motion.all)
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

    def _main_comp(self) -> Optional[dict]:
        """The comp the map is built on (D-40): the scene's main comp, else the comp read last; None = the
        comp open in AE."""
        main = core_lm.main_comp(layer_mapping.store())
        if main is None and _last_ae is not None:
            main = {"id": _last_ae["comp"].get("id"), "name": _last_ae["comp"].get("name")}
        return main

    def _read_ae(self, done, main=True):
        """Ask AE for the main comp's layers (main=False: the comp open in AE; a {id, name}: that comp);
        done(info) with {comp, active, layers} (kept as _last_ae)."""
        if not service.is_connected():
            self.say(u"SyncBridge のサーバーに接続していません。SyncBridge のパネルで Connect を押してください。", error=True)
            return

        asked = main if isinstance(main, dict) else self._main_comp() if main else None

        def reply_to(reply):
            global _last_ae
            if reply["kind"] == "error":
                self.say(reply["data"].get("message") or u"AE のレイヤーを読み込めませんでした。", error=True)
                return
            data = reply["data"]
            if asked is not None and not core_lm.same_comp(asked, data.get("comp")):
                # an old hub or AE panel drops the main comp and answers the comp open in AE (the user,
                # 2026-10-26: the main comp turned into the precomp opened to select the BG)
                self.say(u"AE からメインのコンポ「%s」ではなく「%s」が返りました。ハブか AE のパネルが古い版です。"
                         u"モニターでハブを止め、AE を再起動してから Connect し直してください（何も変えていません）。"
                         % (asked.get("name"), (data.get("comp") or {}).get("name")), error=True)
                return
            _last_ae = {"comp": data["comp"], "layers": data["layers"]}
            done(dict(data))
        try:
            service.request_ae_layers(reply_to, asked)
        except Exception as exc:
            self.say(u"AE のレイヤーを読み込めませんでした: %s" % exc, error=True)

    def load_ae_layers(self):
        """The comp open in AE becomes the main comp (D-40): open the outermost comp, the one with the camera
        work, and press this. Links recorded from a comp inside it are offered their path from it."""
        self.say(u"AE のレイヤーを読み込んでいます…")

        def done(info):
            comp = info["comp"]
            outer = self._ask_outer(comp)
            if outer is not None:                      # read the outer comp instead (and ask again above it)
                self.say(u"AE のコンプ「%s」を読み込んでいます…" % outer.get("name"))
                self._read_ae(done, main=outer)
                return
            text = u"AE のコンプ「%s」をメインのコンポにして、レイヤーを %d 個読み込みました。" % (
                comp.get("name"), len(info["layers"]))
            try:
                current = layer_mapping.store().get("main_comp")
                if not core_lm.same_comp(current, comp):
                    layer_mapping.set_main_comp(comp)
                text += self._offer_reroute(info)
            except Exception as exc:
                self.say(u"メインのコンポを記録できませんでした: %s" % exc, error=True)
                self.refresh()
                return
            self.say(text)
            service.announce("layer_map")
            self.refresh()
        self._read_ae(done, main=False)

    def _ask_outer(self, comp: dict) -> Optional[dict]:
        """The comp read as the main comp is a precomp of other comps (H-AE-33): offer them. AE may take
        another comp than the one the user meant as the open one (the user, 2026-10-26: the precomp was read
        while "camera" was chosen, and the camera PAN was lost). None = keep this comp."""
        outers = comp.get("usedIn") or []
        if not outers:
            return None
        keep = u"「%s」のまま（メインにする）" % comp.get("name")
        items = [u"「%s」" % o.get("name") for o in outers] + [keep]
        text = (u"読み込んだコンポ「%s」は、ほかのコンポの中でプリコンポとして使われています。\n"
                u"カメラワーク（PAN）は外側のコンポに付いていることが多いので、いちばん外のコンポをメインにしてください。\n"
                u"どれをメインのコンポにしますか？" % comp.get("name"))
        name, ok = QtWidgets.QInputDialog.getItem(self, "SyncBridge", text, items, 0, False)
        if not ok or name == keep:
            return None
        return outers[items.index(name)]

    def _offer_reroute(self, info) -> str:
        """Ask to give the links recorded from a comp inside the main comp their path from it."""
        found = core_lm.reroutes(layer_mapping.store(), info)
        text = u""
        if found["fix"]:
            names = u"、".join(layer_map_view.ae_title(new) for _, new in found["fix"])
            answer = QtWidgets.QMessageBox.question(
                self, "SyncBridge",
                u"%d 個の AE のレイヤーが、メインのコンポ「%s」の中のコンポを基準に記録されています。\n"
                u"このままだと、メインのコンポでの動き（プリコンポを動かしたカメラワークなど）が転送に入りません。\n\n"
                u"メインのコンポからの経路に直しますか？\n%s\n\n"
                u"（相対モードの接続は基準を記録し直す必要があります。Ctrl+Z で戻せます）"
                % (len(found["fix"]), info["comp"].get("name"), names))
            if answer == QtWidgets.QMessageBox.StandardButton.Yes:
                n = layer_mapping.reroute_ae_layers(found["fix"])
                text += u"\n%d 個をメインのコンポからの経路に直しました（接続 %d 本）: %s" % (len(found["fix"]), n, names)
        rest = found["many"] + found["missing"]
        if rest:
            text += (u"\n⚠ メインのコンポの外で記録されたままのものがあります（%s）。外側の動きは転送に入りません。"
                     u"つなぎ直してください。" % u"、".join(layer_map_view.ae_title(a) for a in rest))
        return text

    def add_ae_selection(self):
        """Put the layers selected in AE on the map (D-40), with their path from the main comp."""
        self.say(u"AE で選んでいるレイヤーを読み込んでいます…")

        def done(info):
            main, active = info["comp"], info.get("active")
            aes = core_lm.selected_in_ae(info)
            if not aes:
                inside = active is not None and any(layer.get("comp_id") == active.get("id")
                                                    for layer in info["layers"])
                if active is None:
                    text = u"AE でコンポを開き、レイヤーを選んでから押してください。"
                elif active.get("id") != main.get("id") and not inside:
                    text = (u"AE で開いているコンポ「%s」は、このマップのメインのコンポ「%s」の中にありません"
                            u"（4 段以上深いプリコンポも探しません）。メインのコンポの中のプリコンポを開いて選んでください。"
                            % (active.get("name"), main.get("name")))
                else:
                    text = u"AE のコンポ「%s」でレイヤーが選ばれていません。BG やキャラのレイヤーを選んでから押してください。" \
                        % active.get("name")
                self.say(text, error=True)
                self.refresh()
                return
            try:
                added = layer_mapping.show_ae_layers(aes)
            except Exception as exc:
                self.say(u"マップに追加できませんでした: %s" % exc, error=True)
                return
            names = [layer_map_view.ae_title(a) for a in aes]
            text = u"%d 個をマップに追加しました（メインのコンポ「%s」）: %s" % (added, main.get("name"), u"、".join(names))
            if added < len(aes):
                text += u"（%d 個はすでにマップにあります）" % (len(aes) - added)
            same = len(set((a.get("comp_id"), a.get("layer_id")) for a in aes))
            if same < len(aes):
                text += (u"\n同じプリコンポがメインのコンポの中で複数の場所に使われているので、経路ごとに追加しました。"
                         u"不要なものは選んで「マップから外す」で外してください。")
            if main.get("usedIn"):
                text += (u"\n⚠ メインのコンポ「%s」は「%s」の中のプリコンポです。外側のコンポでの動き（PAN）は転送に入りません。"
                         u"外側のコンポを開いて「AE のレイヤーを読み込む」を押すと、メインを変えて経路を直せます。"
                         % (main.get("name"), u"」「".join(o.get("name") for o in main["usedIn"])))
            self.say(text + u"（Ctrl+Z で戻せます）", error=bool(main.get("usedIn")))
            service.announce("layer_map")
            self.refresh()
        self._read_ae(done)

    def record_reference(self, mapping_id: str):
        """The reference from AE at Maya's current frame (D-37): any relative link, and the way for a layer
        inside a precomp, whose motion in the main comp the AE panel cannot send."""
        from . import motion
        if not service.is_connected():
            self.say(u"SyncBridge のサーバーに接続していません。SyncBridge のパネルで Connect を押してください。", error=True)
            return
        frame = cmds.currentTime(q=True)
        try:
            q = motion.query(mapping_id, frame, frame, service.time_sync_origin())
        except Exception as exc:
            self.say(u"基準を記録できません: %s" % exc, error=True)
            return

        def done(reply):
            if reply["kind"] == "error":
                self.say(u"AE のレイヤーを読み込めませんでした: %s" % reply["data"].get("message"), error=True)
                return
            try:
                result = motion.record_reference(mapping_id, frame, reply["data"])
            except Exception as exc:
                self.say(u"基準を記録できませんでした: %s" % exc, error=True)
                return
            self.say(_with_warnings(u"%g フレーム（AE の %.3f 秒）の見え方を基準として記録しました: %s（Ctrl+Z で戻せます）。"
                                    % (frame, q["request"]["times"][0], core_lm.describe(result["mapping"])),
                                    result["warnings"]))
            service.announce("layer_map")
            self.refresh()
        try:
            service.request_ae_motion(q["request"], done)
        except Exception as exc:
            self.say(u"AE のレイヤーを読み込めませんでした: %s" % exc, error=True)

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
