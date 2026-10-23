"""Dialogs that stay in front of the SyncBridge panel.

cmds.confirmDialog opened behind the SyncBridge panel (a tool window always above Maya's main
window): the dialog is modal, so Maya could not be used until it was found (2026-10-20, the
confirmation of an AE -> Maya transfer). These Qt dialogs use the visible SyncBridge panel as
their parent (else Maya's main window) and stay on top, also above After Effects when the
transfer was started there.
"""
from __future__ import annotations

from typing import Optional

try:
    from PySide6 import QtCore, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtCore, QtWidgets
    from shiboken2 import wrapInstance

PANEL_OBJECT_NAME = "SyncBridgePanel"       # ui.WINDOW_NAME


def dialog_parent():
    """The visible SyncBridge panel, else Maya's main window, else None."""
    app = QtWidgets.QApplication.instance()
    if app is not None:
        for widget in app.topLevelWidgets():
            if widget.objectName() == PANEL_OBJECT_NAME and widget.isVisible():
                return widget
    try:
        from maya import OpenMayaUI as omui
        ptr = omui.MQtUtil.mainWindow()
        return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr is not None else None
    except Exception:
        return None


def ask(title: str, text: str, ok: str, cancel: str, parent: Optional[object] = None) -> bool:
    """A question with two buttons; True when `ok` is pressed. Esc / closing = cancel."""
    box, ok_button = build_question(title, text, ok, cancel, parent)
    box.raise_()
    box.activateWindow()
    run = getattr(box, "exec", None) or box.exec_          # PySide6 / PySide2
    run()
    return box.clickedButton() is ok_button


def build_question(title: str, text: str, ok: str, cancel: str, parent: Optional[object] = None):
    """The dialog of ask(), not shown yet: (box, ok button). Separate for screenshots of the UI."""
    box = QtWidgets.QMessageBox(parent if parent is not None else dialog_parent())
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QtWidgets.QMessageBox.Question)
    ok_button = box.addButton(ok, QtWidgets.QMessageBox.AcceptRole)
    cancel_button = box.addButton(cancel, QtWidgets.QMessageBox.RejectRole)
    box.setDefaultButton(ok_button)
    box.setEscapeButton(cancel_button)
    box.setWindowFlags(box.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
    # Long Japanese lines (no spaces) were wrapped too narrow and lost their last characters
    # (scene settings confirmation, offscreen mock 2026-10-20): give the text room.
    box.setStyleSheet("QLabel#qt_msgbox_label { min-width: 460px; }")
    return box, ok_button
