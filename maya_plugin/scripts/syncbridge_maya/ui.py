"""Minimal SyncBridge panel for Maya (Phase 1-B; Phase 6 builds the real UI).

    import syncbridge_maya.ui as sbui
    sbui.show()

PySide2 (Maya 2023/2024) or PySide6 (Maya 2025+), R-6.
"""
from __future__ import annotations

from maya import OpenMayaUI as omui
from maya import cmds

import os

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance

from syncbridge import __version__, protocol
from syncbridge.core import layer_mapping as core_layer_mapping
from syncbridge.core import scene_sync
from . import comp_guide, key_markers, layer_mapping, pixel_mapping, service, snapshots

WINDOW_NAME = "SyncBridgePanel"
# <maya folder>/icons next to scripts/ (repository: maya_plugin/icons; release: <install>/maya/icons)
ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
LOGO_FILE = os.path.join(ICON_DIR, "syncbridge_logo.png")
LOGO_SIZE = 32
_window = None


def _logo_label():
    """The SyncBridge icon for the top left corner (empty when the file is missing)."""
    label = QtWidgets.QLabel()
    pixmap = QtGui.QPixmap(LOGO_FILE)
    if not pixmap.isNull():
        label.setPixmap(pixmap.scaled(LOGO_SIZE, LOGO_SIZE, QtCore.Qt.KeepAspectRatio,
                                      QtCore.Qt.SmoothTransformation))
        label.setToolTip("SyncBridge %s" % __version__)
    return label


def _maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr is not None else None


class SyncBridgePanel(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(WINDOW_NAME)
        self.setWindowTitle("SyncBridge %s" % __version__)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Tool)
        if os.path.isfile(LOGO_FILE):
            self.setWindowIcon(QtGui.QIcon(LOGO_FILE))
        self.setMinimumWidth(360)
        self.busy = False
        self._had_ae = False

        self.status = QtWidgets.QLabel()
        self.peer_label = QtWidgets.QLabel()
        self.connect_btn = QtWidgets.QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)

        self.mode = QtWidgets.QComboBox()
        self.mode.addItems(["editable", "precision"])
        self.origin = QtWidgets.QDoubleSpinBox()
        self.origin.setRange(-1e6, 1e6)
        self.origin.setDecimals(2)
        self.origin.setValue(cmds.playbackOptions(q=True, minTime=True))
        self.origin.setToolTip("Maya frame that corresponds to AE comp time 0 and source time 0\n"
                               "(usually the render start frame)")
        self.tolerance = QtWidgets.QDoubleSpinBox()
        self.tolerance.setRange(0.001, 10.0)
        self.tolerance.setDecimals(3)
        self.tolerance.setSingleStep(0.05)
        self.tolerance.setValue(0.1)

        self.to_ae = QtWidgets.QPushButton("Maya  →  AE")
        self.from_ae = QtWidgets.QPushButton("AE  →  Maya")
        self.to_ae.clicked.connect(lambda: self.transfer("maya2ae"))
        self.from_ae.clicked.connect(lambda: self.transfer("ae2maya"))

        self.save_btn = QtWidgets.QPushButton(u"保存")
        self.save_btn.setToolTip(u"今の Scene Time Warp を名前を付けて保存します")
        self.restore_btn = QtWidgets.QPushButton(u"復元…")
        self.restore_btn.setToolTip(u"保存したタイムワープか、転送前の自動バックアップを書き戻します")
        self.retime_btn = QtWidgets.QPushButton(u"範囲変更…")
        self.retime_btn.setToolTip(u"形を保ったまま、キーを指定したフレーム範囲に伸縮します")
        self.save_btn.clicked.connect(self.save_warp)
        self.restore_btn.clicked.connect(self.restore_warp)
        self.retime_btn.clicked.connect(self.retime_warp)

        width, height = comp_guide.last_size()
        self.guide_width, self.guide_height = QtWidgets.QSpinBox(), QtWidgets.QSpinBox()
        for box, value in ((self.guide_width, width), (self.guide_height, height)):
            box.setRange(1, 32768)
            box.setValue(value)
        self.guide_preset = QtWidgets.QComboBox()
        self.guide_preset.addItem(u"プリセット…")
        for name, w, h in comp_guide.PRESETS:
            self.guide_preset.addItem(u"%s  %d x %d" % (name, w, h), (w, h))
        self.guide_preset.activated.connect(self.apply_guide_preset)
        self.show_guide_btn = QtWidgets.QPushButton(u"枠を表示")
        self.show_guide_btn.setToolTip(u"この大きさの枠を、最後にクリックしたビューのカメラに表示します\n"
                                       u"（Maya のレンダー解像度の中央に等倍）")
        self.show_guide_btn.clicked.connect(self.show_guide)
        self.clear_guide_btn = QtWidgets.QPushButton(u"枠を消す")
        self.clear_guide_btn.setToolTip(u"表示中の解像度の枠をビューから消します")
        self.clear_guide_btn.clicked.connect(self.clear_guide)

        # scene settings (D-21) and time slider sync (D-22)
        chosen = _saved_setting_items()
        self.setting_checks = {}
        for item in scene_sync.ITEMS:
            check = QtWidgets.QCheckBox(scene_sync.ITEM_LABELS[item])
            check.setChecked(item in chosen)
            check.toggled.connect(self.save_setting_items)
            self.setting_checks[item] = check
        self.settings_to_ae = QtWidgets.QPushButton(u"設定  Maya → AE")
        self.settings_to_ae.setToolTip(u"チェックした設定を、AE のアクティブなコンプに送ります（AE で確認してから適用）")
        self.settings_from_ae = QtWidgets.QPushButton(u"設定  AE → Maya")
        self.settings_from_ae.setToolTip(u"AE のアクティブなコンプのチェックした設定を、このシーンに適用します（確認してから適用）")
        self.settings_to_ae.clicked.connect(lambda: self.send_settings("maya2ae"))
        self.settings_from_ae.clicked.connect(lambda: self.send_settings("ae2maya"))
        self.time_sync_check = QtWidgets.QCheckBox(u"タイムスライダーを同期")
        self.time_sync_check.setToolTip(u"Maya と AE のどちらで時間を動かしても、もう片方が同じ時間に移ります\n"
                                        u"（Origin frame = AE のコンプの 0 秒。AE のパネルと共通のスイッチ）")
        self.follow_check = QtWidgets.QCheckBox(u"再生中も追従")
        self.follow_check.setToolTip(u"オフ: 再生中は送らず、止めた位置だけを AE に送ります")
        self.time_sync_check.clicked.connect(self.toggle_time_sync)
        self.follow_check.clicked.connect(self.toggle_follow)
        self.origin.valueChanged.connect(service.set_time_origin)
        service.set_time_origin(self.origin.value())

        # Pixel Mapping (D-24): the camera / BG / method used when an AE layer is sent the first time
        self.pm_mode = QtWidgets.QComboBox()
        self.pm_mode.addItem(u"相対（3D の BG・カメラワーク）", "relative")
        self.pm_mode.addItem(u"絶対（BG の板ポリに合わせる）", "absolute")
        self.pm_mode.setToolTip(u"相対: 最初に送ったときの見え方を基準に、AE の BG の 2D の動きをカメラに足します（BG のモデルは何でも可）。\n"
                                u"絶対: BG の画像を貼った板ポリに、画素単位で合わせます。")
        self.pm_camera = QtWidgets.QComboBox()
        self.pm_bg = QtWidgets.QComboBox()
        self.pm_method = QtWidgets.QComboBox()
        for key in ("pan_zoom", "film_roll", "film_translate", "film_offset"):
            self.pm_method.addItem(pixel_mapping.METHOD_LABELS[key], key)
        self.pm_refresh = QtWidgets.QPushButton(u"↻")
        self.pm_refresh.setToolTip(u"シーンのカメラと板ポリの一覧を読み直します")
        self.pm_refresh.setFixedWidth(28)
        self.pm_list = QtWidgets.QListWidget()
        self.pm_list.setWordWrap(True)                 # the long descriptions were cut (mock, 2026-10-25)
        self.pm_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.pm_list.setMaximumHeight(110)
        self.pm_method.setToolTip(u"2D Pan/Zoom: 平行移動と拡大縮小\n"
                                  u"Film Translate・Scale・Roll: 平行移動・拡大縮小・回転（Film Translate / Post Scale / Film Roll）\n"
                                  u"Film Translate / Film Offset: 平行移動だけ")
        self.pm_change_method = QtWidgets.QPushButton(u"方式を変更")
        self.pm_change_method.setToolTip(u"一覧で選んだ対応付けを、上の「方式」に変えます（相対モードは次の送信で基準を取り直します）")
        self.pm_change_method.clicked.connect(self.change_mapping_method)
        self.pm_rebase = QtWidgets.QPushButton(u"基準をやり直す")
        self.pm_rebase.setToolTip(u"相対モード: 選んだ対応付けの基準を消し、次に AE から送ったときの見え方を新しい基準にします")
        self.pm_rebase.clicked.connect(self.reset_reference)
        self.pm_remove = QtWidgets.QPushButton(u"対応付けを削除")
        self.pm_remove.setToolTip(u"選んだ対応付けをこのシーンから消します（カメラの値はそのまま。Ctrl+Z で戻せます）")
        self.pm_refresh.clicked.connect(self.refresh_pixel_mapping)
        self.pm_remove.clicked.connect(self.remove_mapping)
        for combo in (self.pm_mode, self.pm_camera, self.pm_bg, self.pm_method):
            combo.activated.connect(self.save_pixel_mapping_defaults)

        self.markers_label = QtWidgets.QLabel()
        self.markers_label.setWordWrap(True)
        self.clear_markers_btn = QtWidgets.QPushButton(u"マーカーを消す")
        self.clear_markers_btn.setToolTip(u"AE から送ったキーのマーカー（ブックマークとビューの表示）を、このシーンから消します")
        self.clear_markers_btn.clicked.connect(self.clear_markers)

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)

        form = QtWidgets.QFormLayout()
        form.addRow("Mode", self.mode)
        form.addRow("Origin frame", self.origin)
        form.addRow("Tolerance (frames)", self.tolerance)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(_logo_label())                 # top left
        top.addSpacing(4)
        top.addWidget(self.status, 1)
        top.addWidget(self.connect_btn)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.to_ae)
        buttons.addWidget(self.from_ae)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.peer_label)
        layout.addLayout(form)
        layout.addLayout(buttons)
        # The sections scroll when the panel is shorter than they are (Maya on a 1080p screen):
        # squeezed, Qt cut the combo boxes' text (mock, 2026-10-25).
        sections = QtWidgets.QWidget()
        outer = layout
        layout = QtWidgets.QVBoxLayout(sections)
        layout.setContentsMargins(0, 0, 0, 0)
        sync_box = QtWidgets.QGroupBox(u"シーン設定と時間の同期")
        sync_layout = QtWidgets.QVBoxLayout(sync_box)
        checks = QtWidgets.QGridLayout()
        for index, item in enumerate(scene_sync.ITEMS):
            checks.addWidget(self.setting_checks[item], index // 2, index % 2)
        settings_row = QtWidgets.QHBoxLayout()
        settings_row.addWidget(self.settings_to_ae)
        settings_row.addWidget(self.settings_from_ae)
        time_row = QtWidgets.QHBoxLayout()
        time_row.addWidget(self.time_sync_check)
        time_row.addWidget(self.follow_check)
        time_row.addStretch(1)
        sync_layout.addLayout(checks)
        sync_layout.addLayout(settings_row)
        sync_layout.addLayout(time_row)
        layout.addWidget(sync_box)
        warp_box = QtWidgets.QGroupBox("Scene Time Warp")
        warp_row = QtWidgets.QHBoxLayout(warp_box)
        for button in (self.save_btn, self.restore_btn, self.retime_btn):
            warp_row.addWidget(button)
        layout.addWidget(warp_box)
        guide_box = QtWidgets.QGroupBox(u"解像度の枠")
        guide_layout = QtWidgets.QVBoxLayout(guide_box)
        size_row = QtWidgets.QHBoxLayout()
        size_row.addWidget(QtWidgets.QLabel(u"幅"))
        size_row.addWidget(self.guide_width)
        size_row.addWidget(QtWidgets.QLabel(u"高さ"))
        size_row.addWidget(self.guide_height)
        size_row.addWidget(self.guide_preset, 1)
        action_row = QtWidgets.QHBoxLayout()
        action_row.addStretch(1)
        action_row.addWidget(self.show_guide_btn)
        action_row.addWidget(self.clear_guide_btn)
        guide_hint = QtWidgets.QLabel(u"AE のパネルの「解像度の枠を Maya へ」でも表示できます。")
        guide_hint.setWordWrap(True)
        guide_layout.addLayout(size_row)
        guide_layout.addLayout(action_row)
        guide_layout.addWidget(guide_hint)
        layout.addWidget(guide_box)
        pm_box = QtWidgets.QGroupBox(u"Pixel Mapping（BG スライド）")
        pm_layout = QtWidgets.QVBoxLayout(pm_box)
        pm_form = QtWidgets.QFormLayout()
        camera_row = QtWidgets.QHBoxLayout()
        camera_row.addWidget(self.pm_camera, 1)
        camera_row.addWidget(self.pm_refresh)
        pm_form.addRow(u"モード", self.pm_mode)
        pm_form.addRow(u"カメラ", camera_row)
        pm_form.addRow(u"BG の板ポリ", self.pm_bg)
        pm_form.addRow(u"方式", self.pm_method)
        pm_hint = QtWidgets.QLabel(u"AE のパネルで BG のレイヤーを選んで「BG の位置を Maya のカメラへ」を押します。"
                                   u"相対モードでは、最初の 1 回は今の見え方を基準として記録し（カメラは変えません）、"
                                   u"次から AE の BG の動きをカメラに足します。AE と見比べるときは、解像度ゲートを"
                                   u"隠して（Overscan 1.0）見てください。")
        pm_hint.setWordWrap(True)
        pm_remove_row = QtWidgets.QHBoxLayout()
        pm_remove_row.addStretch(1)
        pm_remove_row.addWidget(self.pm_change_method)
        pm_remove_row.addWidget(self.pm_rebase)
        pm_remove_row.addWidget(self.pm_remove)
        pm_layout.addLayout(pm_form)
        pm_layout.addWidget(pm_hint)
        pm_layout.addWidget(self.pm_list)
        pm_layout.addLayout(pm_remove_row)
        layout.addWidget(pm_box)
        markers_box = QtWidgets.QGroupBox(u"AE のキーのマーカー")
        markers_row = QtWidgets.QHBoxLayout(markers_box)
        markers_row.addWidget(self.markers_label, 1)
        markers_row.addWidget(self.clear_markers_btn)
        layout.addWidget(markers_box)
        layout.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(sections)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.log.setMinimumHeight(90)
        outer.addWidget(scroll, 3)
        outer.addWidget(self.log, 1)
        self.resize(440, 820)

        service.add_listener(self.on_event)
        self.refresh()
        self.show_stored_markers()
        self.refresh_pixel_mapping()

    # -- actions -----------------------------------------------------------------
    def toggle_connection(self):
        if service.is_connected():
            service.disconnect()
            return
        self.write("connecting (the server is started if needed)...")
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            welcome = service.connect(start_server=True)
            if welcome.get("note"):
                self.write(welcome["note"])
        except Exception as exc:
            self.write("connect failed: %s" % exc)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self.refresh()

    def options(self) -> dict:
        return {"mode": self.mode.currentText(), "origin": self.origin.value(),
                "tolerance_frames": self.tolerance.value()}

    def transfer(self, direction: str):
        try:
            if direction == "maya2ae":
                service.send_to_ae(self.options())
                self.write("Maya → AE: confirm in After Effects...")
            else:
                service.receive_from_ae(self.options())
                self.write("AE → Maya: waiting for After Effects...")
        except Exception as exc:
            self.write("cannot start the transfer: %s" % exc)
            return
        self.busy = True
        self.refresh()

    # -- scene settings and time slider sync (D-21, D-22) ---------------------------------------
    def setting_items(self):
        return [item for item in scene_sync.ITEMS if self.setting_checks[item].isChecked()]

    def save_setting_items(self, *_args):
        cmds.optionVar(stringValue=(SETTINGS_ITEMS_VAR, ",".join(self.setting_items())))

    def send_settings(self, direction: str):
        items = self.setting_items()
        if not items:
            self.write(u"送る設定を 1 つ以上チェックしてください。")
            return
        try:
            service.send_settings(direction, items, self.origin.value())
        except Exception as exc:
            self.write(u"設定を送れませんでした: %s" % exc)
            return
        self.write(u"設定 Maya → AE: After Effects で確認してください..." if direction == "maya2ae"
                   else u"設定 AE → Maya: 確認ダイアログを待っています...")
        self.busy = True
        self.refresh()

    def toggle_time_sync(self, checked):
        try:
            service.set_time_sync(checked, self.follow_check.isChecked())
        except Exception as exc:
            self.write(u"タイムスライダーの同期を切り替えられませんでした: %s" % exc)
        self.refresh()

    def toggle_follow(self, checked):
        if service.time_sync_state()["enabled"]:
            try:
                service.set_time_sync(True, checked, lead=False)
            except Exception as exc:
                self.write(u"切り替えられませんでした: %s" % exc)

    def _settings_result(self, reply):
        self.busy = False
        if reply["kind"] == "error":
            self.write(u"設定を送れませんでした: %s" % reply["data"].get("message"))
            return
        data = reply["data"]
        arrow = u"Maya → AE" if data.get("direction") == "maya2ae" else u"AE → Maya"
        status = data.get("status")
        if status == "applied":
            self.write(u"設定 %s を適用しました: %s" % (arrow, _changes_text(data.get("changes"))))
        elif status == "unchanged":
            self.write(u"設定 %s: %s" % (arrow, data.get("message") or u"変更はありません。"))
        elif status == "cancelled":
            self.write(u"設定 %s はキャンセルされました（何も変更していません）。" % arrow)
        else:
            self.write(u"設定 %s: %s" % (arrow, status))
        if status == "applied" and data.get("message"):
            self.write(data["message"])
        for w in data.get("warnings") or []:
            self.write(u"注意: %s" % w)

    # -- Pixel Mapping (D-24) -------------------------------------------------------------------
    def refresh_pixel_mapping(self, *_args):
        chosen = layer_mapping.defaults()
        for combo, nodes, current in ((self.pm_camera, layer_mapping.cameras(), chosen["camera"]),
                                      (self.pm_bg, layer_mapping.meshes(), chosen["bg"])):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(u"（選んでください）", None)
            for node in nodes:
                combo.addItem(node.split("|")[-1], node)
            index = combo.findData(current) if current else 0
            combo.setCurrentIndex(max(index, 0))
            combo.blockSignals(False)
        self.pm_method.setCurrentIndex(max(self.pm_method.findData(chosen["method"]), 0))
        self.pm_mode.setCurrentIndex(max(self.pm_mode.findData(chosen["mode"]), 0))
        self.pm_bg.setEnabled(chosen["mode"] == "absolute")
        self.pm_list.clear()
        try:
            mappings = layer_mapping.stored()
        except Exception as exc:
            self.write(u"Pixel Mapping の対応付けを読めませんでした: %s" % exc)
            mappings = []
        for m in mappings:
            item = QtWidgets.QListWidgetItem(core_layer_mapping.describe(m))
            item.setData(QtCore.Qt.UserRole, m["id"])
            self.pm_list.addItem(item)
        if not mappings:
            self.pm_list.addItem(u"このシーンには対応付けがありません")
        self.pm_remove.setEnabled(bool(mappings))
        self.pm_change_method.setEnabled(bool(mappings))
        self.pm_rebase.setEnabled(any(core_layer_mapping.mode_of(m) == "relative" for m in mappings))

    def save_pixel_mapping_defaults(self, *_args):
        try:
            layer_mapping.set_defaults(self.pm_camera.currentData(), self.pm_bg.currentData(),
                                       self.pm_method.currentData(), self.pm_mode.currentData())
            self.pm_bg.setEnabled(self.pm_mode.currentData() == "absolute")
        except Exception as exc:
            self.write(u"選んだカメラか BG を使えません: %s" % exc)

    def change_mapping_method(self):
        item = self.pm_list.currentItem()
        mapping_id = item.data(QtCore.Qt.UserRole) if item else None
        if not mapping_id:
            self.write(u"方式を変える対応付けを一覧で選んでください。")
            return
        method = self.pm_method.currentData()
        try:
            changed = layer_mapping.change_method(mapping_id, method)
        except Exception as exc:
            self.write(u"方式を変えられませんでした: %s" % exc)
            return
        note = u"次に AE から送ったときの見え方を新しい基準にします（カメラは変わりません）。" \
            if core_layer_mapping.mode_of(changed) == "relative" else u""
        self.write(u"方式を %s に変えました: %s。%s" % (pixel_mapping.METHOD_LABELS[method],
                                                    core_layer_mapping.describe(changed), note))
        self.refresh_pixel_mapping()

    def reset_reference(self):
        item = self.pm_list.currentItem()
        mapping_id = item.data(QtCore.Qt.UserRole) if item else None
        if not mapping_id:
            self.write(u"基準をやり直す対応付けを一覧で選んでください。")
            return
        try:
            layer_mapping.reset_reference(mapping_id)
        except Exception as exc:
            self.write(u"基準を消せませんでした: %s" % exc)
            return
        self.write(u"基準を消しました。Maya と AE の見え方を合わせてから、AE で送ると新しい基準になります（カメラは変わりません）。")
        self.refresh_pixel_mapping()

    def remove_mapping(self):
        item = self.pm_list.currentItem()
        mapping_id = item.data(QtCore.Qt.UserRole) if item else None
        if not mapping_id:
            self.write(u"消す対応付けを一覧で選んでください。")
            return
        try:
            layer_mapping.remove(mapping_id)
        except Exception as exc:
            self.write(u"対応付けを消せませんでした: %s" % exc)
            return
        self.write(u"対応付けを消しました: %s（カメラの値はそのまま。Ctrl+Z で戻せます）" % item.text())
        self.refresh_pixel_mapping()

    # -- Scene Time Warp: save / restore / change range ---------------------------------
    def save_warp(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "SyncBridge", u"保存する名前",
                                                  text=snapshots.default_name())
        if not ok:
            return
        try:
            path = snapshots.save(name)
        except Exception as exc:
            self.write(u"保存できませんでした: %s" % exc)
            return
        self.write(u"保存しました: %s" % path)

    def restore_warp(self):
        try:
            items = snapshots.entries()
        except Exception as exc:
            self.write(u"一覧を読めませんでした: %s" % exc)
            return
        if not items:
            self.write(u"保存したタイムワープもバックアップもありません。先に「保存」してください。")
            return
        dialog = RestoreDialog(items, _playback_range(), self)
        if not _exec(dialog):
            return
        path, new_range = dialog.selection()
        self._run_apply(lambda: snapshots.restore(path, new_range), u"復元")

    def retime_warp(self):
        try:
            current = snapshots.current_key_range()
        except Exception as exc:
            self.write(u"Scene Time Warp を読めませんでした: %s" % exc)
            return
        if current is None:
            self.write(u"このシーンには Scene Time Warp がありません。")
            return
        dialog = RangeDialog(u"範囲変更", u"今のキーの範囲: %g〜%g フレーム\n形を保ったまま、次の範囲に伸縮します。" % current,
                             _playback_range(), self)
        if not _exec(dialog):
            return
        start, end = dialog.values()
        self._run_apply(lambda: snapshots.retime_current(start, end), u"範囲変更")

    def _run_apply(self, action, label):
        try:
            result = action()
        except Exception as exc:
            self.write(u"%sできませんでした: %s" % (label, exc))
            return
        if result.get("status") == "applied":
            rb = result.get("app_readback") or {}
            self.write(u"%sしました（読み戻し %s、最大 %.4f f）。元に戻すときは Ctrl+Z を 1 回。"
                       % (label, "PASS" if rb.get("passed") else "FAIL", rb.get("max_error_frames", float("nan"))))
        else:
            self.write(u"%sをキャンセルしました（何も変更していません）" % label)

    def apply_guide_preset(self, index):
        size = self.guide_preset.itemData(index)
        if size:
            self.guide_width.setValue(size[0])
            self.guide_height.setValue(size[1])
        self.guide_preset.setCurrentIndex(0)

    def show_guide(self):
        width, height = self.guide_width.value(), self.guide_height.value()
        try:
            result = comp_guide.show_size(width, height)
        except Exception as exc:
            self.write(u"枠を表示できませんでした: %s" % exc)
            return
        self.write(u"%dx%d の枠を、カメラ %s のビューに表示しました（Maya のレンダー %dx%d）。"
                   % (width, height, result["camera"], result["render"][0], result["render"][1]))
        for w in result.get("warnings") or []:
            self.write(u"注意: %s" % w)

    # -- AE key markers (D-18) ---------------------------------------------------------------
    def show_stored_markers(self):
        """Show the markers stored in this scene (also in the view, where the plug-in draws them)."""
        data = key_markers.stored()
        if not data:
            self.markers_label.setText(u"このシーンにはマーカーがありません。AE のパネルの「キーのマーカーを Maya へ」で送れます。")
            self.clear_markers_btn.setEnabled(False)
            return
        frames = [m["frame"] for m in data.get("markers") or []]
        self.markers_label.setText(u"%s / %s のキー %d 個（フレーム %s〜%s、Origin %s）" % (
            data.get("comp", ""), data.get("layer", ""), len(frames),
            key_markers._frame_text(min(frames)) if frames else "-",
            key_markers._frame_text(max(frames)) if frames else "-", key_markers._frame_text(data.get("origin", 0))))
        self.clear_markers_btn.setEnabled(True)
        try:
            key_markers.restore_overlay()
        except Exception as exc:
            self.write(u"マーカーをビューに表示できませんでした: %s" % exc)

    def clear_markers(self):
        try:
            count = key_markers.clear()
        except Exception as exc:
            self.write(u"マーカーを消せませんでした: %s" % exc)
            return
        self.write(u"キーのマーカー %d 個を消しました（Ctrl+Z で戻せます）。" % count)
        self.show_stored_markers()

    def clear_guide(self):
        try:
            count = comp_guide.clear()
        except Exception as exc:
            self.write(u"枠を消せませんでした: %s" % exc)
            return
        self.write(u"枠を消しました。" if count else u"表示中の枠はありません。")

    # -- events (main thread) ----------------------------------------------------------
    def on_event(self, event, payload):
        if event == "transfer_result":
            self.busy = False
            if payload["kind"] == "error":
                self.write("failed: %s" % payload["data"].get("message"))
            else:
                data = payload["data"]
                self.write(protocol.describe_result(data))
                if data.get("message"):
                    self.write(data["message"])
                for w in (data.get("report") or {}).get("warnings", []):
                    self.write("warning: %s" % w)
        elif event == "disconnected":
            self.busy = False
            self._had_ae = False
            self.write("disconnected: %s" % payload)
        elif event == "connected":
            self.write("connected as %s" % payload.get("client_id"))
        elif event == "request":
            if payload == "apply.request":
                self.write("AE → Maya: confirm the dialog in Maya...")
        elif event == "applied":
            status = payload.get("status")
            if status == "applied":
                rb = payload.get("readback") or {}
                self.write("AE → Maya applied %s keys, readback %s (max %.4f f). Undo once to revert."
                           % (payload.get("keys"), "PASS" if rb.get("passed") else "FAIL",
                              rb.get("max_error_frames", float("nan"))))
            elif status == "cancelled":
                self.write("AE → Maya cancelled (nothing changed)")
            else:
                self.write("AE → Maya failed: %s" % payload.get("message"))
        elif event == "markers":
            if payload.get("status") == "applied":
                self.write(u"AE「%s / %s」のキーのマーカー %d 個を受け取りました（フレーム %s〜%s）。"
                           u"タイムスライダーのブックマークとビューに表示し、シーンに保存されます。取り消しは Ctrl+Z を 1 回。"
                           % (payload.get("comp", ""), payload.get("layer", ""), payload["count"],
                              payload["first"], payload["last"]))
            else:
                self.write(u"キーのマーカーを受け取れませんでした: %s" % payload.get("message"))
            self.show_stored_markers()
        elif event == "guide":
            if payload.get("status") == "applied":
                self.write(u"AE のコンプ「%s」（%dx%d）の枠を、カメラ %s のビューに表示しました（Maya のレンダー %dx%d）。"
                           % (payload.get("name") or "", payload["comp"][0], payload["comp"][1], payload["camera"],
                              payload["render"][0], payload["render"][1]))
                for w in payload.get("warnings") or []:
                    self.write(u"注意: %s" % w)
            else:
                self.write(u"枠を表示できませんでした: %s" % payload.get("message"))
        elif event == "settings_result":
            self._settings_result(payload)
        elif event == "settings_applied":
            status = payload.get("status")
            if status == "applied":
                self.write(u"AE の設定をこのシーンに適用しました: %s。元に戻すときは Ctrl+Z を 1 回。"
                           % _changes_text(payload.get("changes")))
            elif status == "cancelled":
                self.write(u"AE → Maya の設定はキャンセルしました（何も変更していません）。")
            else:
                self.write(u"AE の設定を適用できませんでした: %s" % payload.get("message"))
        elif event == "pixelmap":
            if payload.get("reference_recorded"):
                self.write(u"%s今の見え方を基準として記録しました（カメラは変えていません）: %s。次から AE の BG の動きを足します。"
                           % (u"［新しい対応付け］" if payload.get("created") else u"", payload["mapping"]["text"]))
                for w in payload.get("warnings") or []:
                    self.write(u"注意: %s" % w)
            elif payload.get("status") == "applied":
                values = u"、".join(u"%s %.6g" % (k, v) for k, v in payload["values"].items()
                                   if not isinstance(v, bool))
                self.write(u"%sAE の BG の位置をカメラに設定しました: %s（%s、ずれ %.3f, %.3f px、計算上の誤差 %.1e px）。"
                           u"元に戻すときは Ctrl+Z を 1 回。" % (
                               u"［新しい対応付け］" if payload.get("created") else u"", payload["mapping"]["text"],
                               values, payload["shift_px"][0], payload["shift_px"][1], payload["max_error_px"]))
                for w in payload.get("warnings") or []:
                    self.write(u"注意: %s" % w)
            elif payload.get("status") == "cancelled":
                self.write(u"Pixel Mapping はキャンセルしました（カメラは変えていません）。")
            else:
                self.write(u"AE の BG の位置を設定できませんでした: %s" % payload.get("message"))
            self.refresh_pixel_mapping()
        elif event == "time_sync_stats":
            self.write(u"同期の計測（Maya が受け取った分）: %s" % payload)
        elif event == "time_sync":
            self.write(u"タイムスライダーの同期: %s" % (
                (u"オン" + (u"（再生中も追従）" if payload.get("follow_playback") else u""))
                if payload.get("enabled") else u"オフ"))
        elif event == "peers":
            ae_now = [p for p in payload if p["app"] == "ae"]
            if bool(ae_now) != self._had_ae:
                self.write("After Effects %s" % ("connected" if ae_now else "disconnected"))
            self._had_ae = bool(ae_now)
        elif event == "error":
            self.write("error: %s" % payload.get("message"))
        self.refresh()

    def refresh(self):
        connected = service.is_connected()
        if connected:
            self.status.setText("Server: connected (%s)" % service.client().client_id)
        else:
            self.status.setText("Server: not connected")
        self.connect_btn.setText("Disconnect" if connected else "Connect")
        ae = [p for p in service.peers() if p["app"] == "ae"]
        if not connected:
            self.peer_label.setText("")
        elif ae:
            self.peer_label.setText("After Effects: connected (%s)" % (ae[-1].get("document") or ae[-1]["client_id"]))
        else:
            self.peer_label.setText("After Effects: not connected")
        enabled = connected and bool(ae) and not self.busy
        self.to_ae.setEnabled(enabled)
        self.from_ae.setEnabled(enabled)
        self.settings_to_ae.setEnabled(enabled)
        self.settings_from_ae.setEnabled(enabled)
        state = service.time_sync_state()
        for check, value in ((self.time_sync_check, state["enabled"]), (self.follow_check, state["follow_playback"])):
            check.blockSignals(True)
            check.setChecked(bool(value))
            check.blockSignals(False)
        self.time_sync_check.setEnabled(connected)
        self.follow_check.setEnabled(connected)

    def write(self, text: str):
        self.log.appendPlainText(str(text))

    def closeEvent(self, event):
        service.remove_listener(self.on_event)
        super().closeEvent(event)


def _playback_range():
    return (cmds.playbackOptions(q=True, minTime=True), cmds.playbackOptions(q=True, maxTime=True))


SETTINGS_ITEMS_VAR = "syncBridgeSettingsItems"


def _saved_setting_items():
    """The settings checked last time (all of them the first time)."""
    if cmds.optionVar(exists=SETTINGS_ITEMS_VAR):
        return [i for i in str(cmds.optionVar(q=SETTINGS_ITEMS_VAR)).split(",") if i]
    return list(scene_sync.ITEMS)


def _changes_text(changes) -> str:
    return u"、".join(u"%s %s → %s" % (c["label"], c["before"], c["after"]) for c in changes or []) or u"変更なし"


def _exec(dialog) -> bool:
    run = getattr(dialog, "exec", None) or dialog.exec_      # PySide6 / PySide2
    return bool(run())


def _range_inputs(default):
    start, end = QtWidgets.QDoubleSpinBox(), QtWidgets.QDoubleSpinBox()
    for box, value in ((start, default[0]), (end, default[1])):
        box.setRange(-1e6, 1e6)
        box.setDecimals(2)
        box.setValue(value)
    return start, end


class RangeDialog(QtWidgets.QDialog):
    """Start / end frames, defaulting to the playback range."""

    def __init__(self, title, text, default, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SyncBridge - %s" % title)
        self.start, self.end = _range_inputs(default)
        form = QtWidgets.QFormLayout()
        form.addRow(u"開始フレーム", self.start)
        form.addRow(u"終了フレーム", self.end)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(text))
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self):
        return self.start.value(), self.end.value()

    def _accept(self):
        if self.end.value() <= self.start.value():
            QtWidgets.QMessageBox.warning(self, "SyncBridge", u"終了フレームは開始フレームより後にしてください。")
            return
        self.accept()


class RestoreDialog(QtWidgets.QDialog):
    """Pick a saved warp or an automatic backup; optionally stretch it to a frame range."""

    def __init__(self, items, default_range, parent=None):
        super().__init__(parent)
        self.setWindowTitle(u"SyncBridge - 復元")
        self.setMinimumWidth(560)
        self.items = items
        self.list = QtWidgets.QListWidget()
        for item in items:
            tag = u"保存" if item["kind"] == "snapshot" else u"バックアップ"
            text = u"[%s] %s   %g〜%g f → %g〜%g   %d キー   %s   %s" % (
                tag, item["name"], item["frames"][0], item["frames"][1], item["values"][0], item["values"][1],
                item["keys"], item["modified"].strftime("%Y-%m-%d %H:%M"), item["scene"])
            self.list.addItem(text)
        self.list.setCurrentRow(0)
        self.stretch = QtWidgets.QCheckBox(u"範囲を変更して復元する（形を保ったまま伸縮）")
        self.start, self.end = _range_inputs(default_range)
        self.start.setEnabled(False)
        self.end.setEnabled(False)
        self.stretch.toggled.connect(self.start.setEnabled)
        self.stretch.toggled.connect(self.end.setEnabled)
        form = QtWidgets.QFormLayout()
        form.addRow(u"開始フレーム", self.start)
        form.addRow(u"終了フレーム", self.end)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(u"書き戻すタイムワープを選んでください（新しい順）。\n"
                                          u"表示: キーの範囲（シーンのフレーム）→ 値の範囲（ワープ後のフレーム）"))
        layout.addWidget(self.list, 1)
        layout.addWidget(self.stretch)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def selection(self):
        path = self.items[self.list.currentRow()]["path"]
        new_range = (self.start.value(), self.end.value()) if self.stretch.isChecked() else None
        return path, new_range

    def _accept(self):
        if self.list.currentRow() < 0:
            return
        if self.stretch.isChecked() and self.end.value() <= self.start.value():
            QtWidgets.QMessageBox.warning(self, "SyncBridge", u"終了フレームは開始フレームより後にしてください。")
            return
        self.accept()


def show() -> SyncBridgePanel:
    global _window
    if _window is not None:
        try:
            _window.close()
            _window.deleteLater()
        except RuntimeError:   # already deleted by Qt
            pass
    _window = SyncBridgePanel(_maya_main_window())
    _window.show()
    return _window
