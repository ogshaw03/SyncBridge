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
from . import service

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
