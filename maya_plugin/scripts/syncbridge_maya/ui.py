"""Minimal SyncBridge panel for Maya (Phase 1-B; Phase 6 builds the real UI).

    import syncbridge_maya.ui as sbui
    sbui.show()

PySide2 (Maya 2023/2024) or PySide6 (Maya 2025+), R-6.
"""
from __future__ import annotations

from maya import OpenMayaUI as omui
from maya import cmds

try:
    from PySide6 import QtCore, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtCore, QtWidgets
    from shiboken2 import wrapInstance

from syncbridge import __version__, protocol
from . import service, snapshots

WINDOW_NAME = "SyncBridgePanel"
_window = None


def _maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr is not None else None


class SyncBridgePanel(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(WINDOW_NAME)
        self.setWindowTitle("SyncBridge %s" % __version__)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Tool)
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

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)

        form = QtWidgets.QFormLayout()
        form.addRow("Mode", self.mode)
        form.addRow("Origin frame", self.origin)
        form.addRow("Tolerance (frames)", self.tolerance)
        top = QtWidgets.QHBoxLayout()
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
        warp_box = QtWidgets.QGroupBox("Scene Time Warp")
        warp_row = QtWidgets.QHBoxLayout(warp_box)
        for button in (self.save_btn, self.restore_btn, self.retime_btn):
            warp_row.addWidget(button)
        layout.addWidget(warp_box)
        layout.addWidget(self.log, 1)

        service.add_listener(self.on_event)
        self.refresh()

    # -- actions -----------------------------------------------------------------
    def toggle_connection(self):
        if service.is_connected():
            service.disconnect()
            return
        self.write("connecting (the server is started if needed)...")
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            service.connect(start_server=True)
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

    def write(self, text: str):
        self.log.appendPlainText(str(text))

    def closeEvent(self, event):
        service.remove_listener(self.on_event)
        super().closeEvent(event)


def _playback_range():
    return (cmds.playbackOptions(q=True, minTime=True), cmds.playbackOptions(q=True, maxTime=True))


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
