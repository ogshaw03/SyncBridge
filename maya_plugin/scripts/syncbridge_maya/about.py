"""About SyncBridge / update, from the panel's menu bar (D-46, TEMPORARY: the update steps may change).

The releases on GitHub (syncbridge.updater.releases), newest first; the chosen one is downloaded and its
installer started (the setup's wizard, or the zip's Install.bat). The network runs in a thread so Maya
does not wait on it.

    import syncbridge_maya.about as about
    about.show(parent)
"""
from __future__ import annotations

import os
import threading
import webbrowser
from typing import Callable, Optional

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

from syncbridge import __version__
from syncbridge.updater import install, releases

KIND_TEXT = {"exe": u"インストーラー", "zip": u"zip"}
RELATION_TEXT = {"current": u"使用中", "newer": u"新しい版", "older": u""}
_dialog = None


class _Relay(QtCore.QObject):
    """Results of the worker thread, delivered in Maya's (the GUI) thread."""
    done = QtCore.Signal(object, object)          # result, error
    progress = QtCore.Signal(int, int)


def _in_thread(work: Callable, on_done: Callable, on_progress: Optional[Callable] = None) -> _Relay:
    relay = _Relay()
    relay.done.connect(on_done)
    if on_progress:
        relay.progress.connect(on_progress)

    def run():
        try:
            result = work(relay.progress.emit)
        except Exception as exc:                # shown to the user, never raised into Maya
            relay.done.emit(None, exc)
        else:
            relay.done.emit(result, None)
    threading.Thread(target=run, daemon=True).start()
    return relay


class AboutDialog(QtWidgets.QDialog):
    """`load` returns parse_releases' list (tests and mocks give their own)."""

    def __init__(self, parent=None, load: Optional[Callable] = None, logo: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle(u"SyncBridge について")
        self.setMinimumWidth(460)
        self._load = load or (lambda: releases.releases(__version__))
        self._relays = []                          # kept alive until their thread is done
        self.items = []

        head = QtWidgets.QHBoxLayout()
        if logo and os.path.isfile(logo):
            icon = QtWidgets.QLabel()
            icon.setPixmap(QtGui.QPixmap(logo).scaled(40, 40, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
            head.addWidget(icon)
        title = QtWidgets.QLabel(u"<b style='font-size:15px'>SyncBridge</b> <span style='color:#9a9a9a'>%s</span><br>"
                                 u"<span style='color:#a8a8a8'>Maya と After Effects をつなぐツール</span>" % __version__)
        head.addWidget(title, 1)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels([u"版", u"公開日", u"ファイル", u""])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        for col, width in ((0, 90), (1, 100), (2, 110)):
            self.tree.header().resizeSection(col, width)
        self.tree.setMinimumHeight(180)
        self.tree.currentItemChanged.connect(self._show_selected)
        self.notes = QtWidgets.QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setMaximumHeight(90)
        self.notes.setPlaceholderText(u"リリースノート")
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)

        self.update_btn = QtWidgets.QPushButton(u"インストール")
        self.update_btn.setStyleSheet("QPushButton { background: #3f6d8f; font-weight: bold; } "
                                      "QPushButton:disabled { background: #4a4a4a; }")
        self.update_btn.setToolTip(u"選んだ版のインストーラー（なければ zip）を GitHub からダウンロードして開きます")
        self.update_btn.clicked.connect(self.update_to_selected)
        page_btn = QtWidgets.QPushButton(u"リリースのページ")
        page_btn.setToolTip(releases.PAGE_URL)
        page_btn.clicked.connect(lambda: webbrowser.open(releases.PAGE_URL))
        self.reload_btn = QtWidgets.QPushButton(u"再読み込み")
        self.reload_btn.clicked.connect(self.reload)
        close_btn = QtWidgets.QPushButton(u"閉じる")
        close_btn.clicked.connect(self.close)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(head)
        layout.addWidget(QtWidgets.QLabel(u"GitHub のリリース"))
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.notes)
        layout.addWidget(self.status)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.update_btn)
        buttons.addWidget(page_btn)
        buttons.addWidget(self.reload_btn)
        buttons.addStretch(1)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)
        self.resize(500, 460)
        self._show_selected()
        self.reload()

    # -- the list ----------------------------------------------------------------------------------------
    def reload(self):
        self.reload_btn.setEnabled(False)
        self.say(u"GitHub からリリースの一覧を取得しています…")
        self._relays.append(_in_thread(lambda _progress: self._load(), self._loaded))

    def _loaded(self, items, error):
        self.reload_btn.setEnabled(True)
        if error is not None:
            self.say(str(error), error=True)
            return
        self.set_items(items)

    def set_items(self, items):
        self.items = list(items or [])
        self.tree.clear()
        for item in self.items:
            asset = item.get("asset")
            row = QtWidgets.QTreeWidgetItem([
                item["version"], item.get("date") or "", KIND_TEXT.get(asset["kind"], "") if asset else u"（なし）",
                RELATION_TEXT.get(item.get("relation") or "", "")])
            if item.get("relation") == "current":
                font = row.font(0)
                font.setBold(True)
                for col in range(4):
                    row.setFont(col, font)
            if item.get("prerelease"):
                row.setToolTip(0, u"プレリリース")
            self.tree.addTopLevelItem(row)
        newer = [i for i in self.items if i.get("relation") == "newer"]
        if not self.items:
            self.say(u"GitHub にリリースがありません。")
        elif newer:
            self.say(u"新しい版があります: %s" % newer[0]["version"])
        else:
            self.say(u"使用中の %s が最新です（古い版に戻すこともできます）。" % __version__)
        if self.items:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def selected(self) -> Optional[dict]:
        row = self.tree.currentItem()
        return self.items[self.tree.indexOfTopLevelItem(row)] if row is not None else None

    def _show_selected(self, *_args):
        item = self.selected()
        self.notes.setPlainText((item or {}).get("notes") or "")
        self.update_btn.setEnabled(bool(item and item.get("asset") and item.get("relation") != "current"))

    def say(self, text: str, error: bool = False):
        self.status.setStyleSheet("color: #e08a40;" if error else "color: #a8a8a8;")
        self.status.setText(text)

    # -- update ------------------------------------------------------------------------------------------
    def confirm_text(self, item: dict) -> str:
        kind = item["asset"]["kind"]
        older = item.get("relation") == "older"
        lines = [u"SyncBridge %s をインストールします（今は %s%s）。" % (item["version"], __version__,
                                                                u"。古い版に戻ります" if older else u""), u""]
        if kind == "exe":
            lines += [u"インストーラーをダウンロードして開きます。",
                      u"インストーラーが開いたら、Maya と After Effects を終了してから「インストール」を押してください。"]
        else:
            lines += [u"zip をダウンロードして展開し、Install.bat を実行します（すぐにインストールが始まります）。",
                      u"終わったら、Maya と After Effects を再起動してください。"]
        lines += [u"", u"インストール中は SyncBridge のサーバーが止まり、Maya と After Effects の接続が切れます。"]
        if not item.get("has_updater", True):
            lines += [u"", u"※ %s にはこの更新のメニューがありません。あとで新しい版にするときは、インストーラーか zip を"
                           u"自分で実行してください。" % item["version"]]
        return u"\n".join(lines)

    def update_to_selected(self):
        item = self.selected()
        if not item or not item.get("asset"):
            return
        answer = QtWidgets.QMessageBox.question(self, u"SyncBridge の更新", self.confirm_text(item),
                                                QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
        if answer != QtWidgets.QMessageBox.Ok:
            return
        self.update_btn.setEnabled(False)
        progress = QtWidgets.QProgressDialog(u"%s をダウンロードしています…" % item["asset"]["name"], "", 0, 100, self)
        progress.setWindowTitle(u"SyncBridge の更新")
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.show()

        def on_progress(done, total):
            progress.setValue(int(done * 100 / total) if total else 0)

        def work(report):
            path = install.download(item["asset"], progress=report)
            return install.launch(path)

        def finished(kind, error):
            progress.close()
            self._show_selected()
            if error is not None:
                self.say(str(error), error=True)
                QtWidgets.QMessageBox.warning(self, u"SyncBridge の更新", str(error))
                return
            if kind == "exe":
                text = (u"インストーラーを開きました。Maya と After Effects を終了してから「インストール」を押し、"
                        u"終わったら起動し直してください。")
            else:
                text = u"インストールを始めました。完了のメッセージが出たら、Maya と After Effects を再起動してください。"
            self.say(text)
            QtWidgets.QMessageBox.information(self, u"SyncBridge の更新", text)
        self._relays.append(_in_thread(work, finished, on_progress))


def show(parent=None, logo: Optional[str] = None) -> AboutDialog:
    global _dialog
    if _dialog is not None:
        try:
            _dialog.close()
        except RuntimeError:                    # already deleted by Qt
            pass
    _dialog = AboutDialog(parent, logo=logo)
    _dialog.show()
    return _dialog
