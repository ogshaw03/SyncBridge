"""The confirmation of the delivery cleanup (D-47): what goes, and what to do with the dedicated cameras.

    keep_cameras = cleanup_dialog.ask(cleanup.inventory())     None when cancelled
"""
from __future__ import annotations

from typing import Optional

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets

from . import cleanup
from .dialogs import dialog_parent

NOTE_STYLE = "color: #a8a8a8;"


class CleanupDialog(QtWidgets.QDialog):
    def __init__(self, found: dict, parent=None):
        super().__init__(parent if parent is not None else dialog_parent())
        self.setWindowTitle(u"納品用のクリーンアップ")
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(u"SyncBridge がこのシーンに作ったものを消します。"))
        lines = cleanup.summary_lines(found)
        if lines:
            items = QtWidgets.QLabel(u"\n".join(u"・" + line for line in lines))
            layout.addWidget(items)

        self.keep = QtWidgets.QRadioButton(u"普通のカメラとして残す（キーと見え方はそのまま）")
        self.delete = QtWidgets.QRadioButton(u"消す（SyncBridge で付けた 2D の動きも消えます）")
        self.keep.setChecked(True)
        cameras = found["cameras"]
        if cameras:
            box = QtWidgets.QGroupBox(u"専用カメラ（%d 台）" % len(cameras))
            inner = QtWidgets.QVBoxLayout(box)
            names = QtWidgets.QLabel(u"、".join(
                u"%s（キー %d）" % (c["name"], c["keys"]) if c["keys"] else c["name"] for c in cameras))
            names.setWordWrap(True)
            inner.addWidget(names)
            inner.addWidget(self.keep)
            inner.addWidget(self.delete)
            note = QtWidgets.QLabel(u"レンダーに使っているときは「残す」を選んでください")
            note.setStyleSheet(NOTE_STYLE)
            inner.addWidget(note)
            layout.addWidget(box)

        note = QtWidgets.QLabel(u"Scene Time Warp、ご自分のノードやブックマークは残します。開いているビューアーと"
                                u"レイヤーマップは閉じます。取り消し 1 回で戻せます。\n"
                                u"終わったら、そのまま保存してください（SyncBridge の操作を続けると、また作られるものがあります）。")
        note.setWordWrap(True)
        note.setStyleSheet(NOTE_STYLE)
        layout.addWidget(note)

        buttons = QtWidgets.QDialogButtonBox()
        self.ok_button = buttons.addButton(u"クリーンアップ", QtWidgets.QDialogButtonBox.AcceptRole)
        buttons.addButton(u"キャンセル", QtWidgets.QDialogButtonBox.RejectRole)
        self.ok_button.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setMinimumWidth(460)

    def keep_cameras(self) -> bool:
        return self.keep.isChecked()


def ask(found: dict, parent=None) -> Optional[bool]:
    """Whether to keep the dedicated cameras; None when cancelled."""
    dialog = CleanupDialog(found, parent)
    dialog.raise_()
    dialog.activateWindow()
    run = getattr(dialog, "exec", None) or dialog.exec_          # PySide6 / PySide2
    if not run():
        return None
    return dialog.keep_cameras()
