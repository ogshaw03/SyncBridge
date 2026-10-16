"""The monitor window (PySide6). Everything that talks to a hub runs on a worker thread and
comes back through queued signals, so a hung hub never freezes the window.
"""
from __future__ import annotations

import os
import sys
import threading
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QHBoxLayout,
                               QHeaderView, QLabel, QMainWindow, QMessageBox, QPlainTextEdit,
                               QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from .. import __version__, hubs
from ..server import session
from . import model

REFRESH_MS = 5000
TITLE = "SyncBridge モニター"


class Bridge(QObject):
    """Signals emitted from worker threads, delivered on the main thread."""
    hubs_found = Signal(object)            # List[hubs.HubInfo]
    hub_loaded = Signal(int, object)       # pid, dict from model.load_hub or an Exception
    event = Signal(int, object)            # pid, event dict
    stream_closed = Signal(int, str)       # pid, reason
    action_done = Signal(str, object)      # what, None or an Exception


def _run(target, *args) -> None:
    threading.Thread(target=target, args=args, daemon=True).start()


def _table(columns: List[str]) -> QTableWidget:
    t = QTableWidget(0, len(columns))
    t.setHorizontalHeaderLabels(columns)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    return t


def _fill(table: QTableWidget, rows: List[List[str]], keys: Optional[List[object]] = None) -> None:
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            item = QTableWidgetItem(text)
            if keys is not None and c == 0:
                item.setData(Qt.UserRole, keys[r])
            table.setItem(r, c, item)


class MonitorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("%s %s" % (TITLE, __version__))
        self.resize(1100, 720)
        self.bridge = Bridge()
        self.bridge.hubs_found.connect(self._on_hubs_found)
        self.bridge.hub_loaded.connect(self._on_hub_loaded)
        self.bridge.event.connect(self._on_event)
        self.bridge.stream_closed.connect(self._on_stream_closed)
        self.bridge.action_done.connect(self._on_action_done)

        self.hubs: Dict[int, hubs.HubInfo] = {}
        self.selected: Optional[int] = None
        self.view = model.HubView()
        self.stream: Optional[model.EventStream] = None
        self._discovering = False
        self.no_admin = set()          # pids of hubs without the admin API (0.1.x)

        self._build()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(REFRESH_MS)
        self.refresh()

    # ---- layout ----------------------------------------------------------------------
    def _build(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)

        top = QHBoxLayout()
        top.addWidget(QLabel("動作中のハブ"))
        top.addStretch(1)
        self.auto = QCheckBox("自動更新（5 秒）")
        self.auto.setChecked(True)
        self.auto.toggled.connect(lambda on: self.timer.start(REFRESH_MS) if on else self.timer.stop())
        top.addWidget(self.auto)
        refresh = QPushButton("更新")
        refresh.clicked.connect(self.refresh)
        top.addWidget(refresh)
        layout.addLayout(top)

        self.hub_table = _table(model.HUB_COLUMNS)
        self.hub_table.itemSelectionChanged.connect(self._on_hub_selection)

        buttons = QHBoxLayout()
        self.stop_btn = QPushButton("停止")
        self.stop_btn.clicked.connect(self._stop_hub)
        self.kill_btn = QPushButton("強制終了…")
        self.kill_btn.clicked.connect(self._kill_hub)
        self.clean_btn = QPushButton("残ったファイルを片付け")
        self.clean_btn.clicked.connect(self._clean_hub)
        folder_btn = QPushButton("ログフォルダを開く")
        folder_btn.clicked.connect(self._open_logs)
        for b in (self.stop_btn, self.kill_btn, self.clean_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        buttons.addWidget(folder_btn)

        hub_box = QWidget()
        hub_layout = QVBoxLayout(hub_box)
        hub_layout.setContentsMargins(0, 0, 0, 0)
        hub_layout.addWidget(self.hub_table)
        hub_layout.addLayout(buttons)

        self.detail = QLabel("")
        self.tabs = QTabWidget()

        clients = QWidget()
        cl = QVBoxLayout(clients)
        self.client_table = _table(model.CLIENT_COLUMNS)
        self.client_table.itemSelectionChanged.connect(self._update_buttons)
        self.disconnect_btn = QPushButton("切断…")
        self.disconnect_btn.clicked.connect(self._disconnect_client)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.disconnect_btn)
        cl.addWidget(self.client_table)
        cl.addLayout(row)
        self.tabs.addTab(clients, "接続中のアプリ")

        self.transfer_table = _table(model.TRANSFER_COLUMNS)
        self.tabs.addTab(self.transfer_table, "転送の履歴")

        logs = QWidget()
        ll = QVBoxLayout(logs)
        filt = QHBoxLayout()
        filt.addWidget(QLabel("表示するレベル"))
        self.level = QComboBox()
        self.level.addItems(model.LEVELS[:-1])
        self.level.setCurrentText("INFO")
        self.level.currentTextChanged.connect(lambda _t: self._render_log())
        filt.addWidget(self.level)
        filt.addStretch(1)
        ll.addLayout(filt)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(model.MAX_LOG)
        self.log_text.setLineWrapMode(QPlainTextEdit.NoWrap)
        ll.addWidget(self.log_text)
        self.tabs.addTab(logs, "ログ")

        detail_box = QWidget()
        dl = QVBoxLayout(detail_box)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.addWidget(self.detail)
        dl.addWidget(self.tabs)

        split = QSplitter(Qt.Vertical)
        split.addWidget(hub_box)
        split.addWidget(detail_box)
        split.setStretchFactor(1, 2)
        layout.addWidget(split)
        self.setCentralWidget(root)
        self.statusBar()
        self._update_buttons()

    # ---- hub list --------------------------------------------------------------------
    def refresh(self) -> None:
        if self._discovering:
            return
        self._discovering = True
        _run(self._discover)

    def _discover(self) -> None:
        try:
            found = hubs.discover()
        except Exception as exc:     # never kill the worker silently
            found = exc
        self.bridge.hubs_found.emit(found)

    def _on_hubs_found(self, found) -> None:
        self._discovering = False
        if isinstance(found, Exception):
            self.statusBar().showMessage("ハブを探せませんでした: %s" % found)
            return
        previous = self.hubs.get(self.selected) if self.selected is not None else None
        self.hubs = {h.pid: h for h in found}
        keep = self.selected
        self.hub_table.blockSignals(True)
        _fill(self.hub_table, [model.hub_row(h.to_json()) for h in found], [h.pid for h in found])
        self.hub_table.blockSignals(False)
        self.statusBar().showMessage("ハブ %d 個（%s 更新）" % (len(found), model.local_time(hubs_now())))
        if keep in self.hubs:
            self._select_row(keep)
            if previous is not None and previous.state != self.hubs[keep].state:
                self._select_hub(keep)           # e.g. it stopped responding
        elif found:
            self._select_row(found[0].pid)
            self._select_hub(found[0].pid)
        else:
            self._select_hub(None)
        self._update_buttons()

    def _select_row(self, pid: int) -> None:
        self.hub_table.blockSignals(True)
        for r in range(self.hub_table.rowCount()):
            if self.hub_table.item(r, 0).data(Qt.UserRole) == pid:
                self.hub_table.selectRow(r)
        self.hub_table.blockSignals(False)

    def _on_hub_selection(self) -> None:
        rows = self.hub_table.selectionModel().selectedRows()
        pid = self.hub_table.item(rows[0].row(), 0).data(Qt.UserRole) if rows else None
        if pid != self.selected:
            self._select_hub(pid)

    # ---- selected hub ----------------------------------------------------------------
    def _select_hub(self, pid: Optional[int]) -> None:
        if self.stream is not None:
            self.stream.stop()
            self.stream = None
        self.selected = pid
        self.view = model.HubView()
        self._render_all()
        hub = self.hubs.get(pid) if pid is not None else None
        if hub is None:
            self.detail.setText("ハブが選ばれていません。")
        elif hub.state == hubs.RUNNING:
            self.detail.setText("ハブ PID %d（ポート %s）を読み込み中…" % (hub.pid, hub.port))
            _run(self._load, hub)
        else:
            self.detail.setText("ハブ PID %d: %s。詳細は表示できません。"
                                % (hub.pid, model.STATE_LABELS.get(hub.state, hub.state)))
        self._update_buttons()

    def _load(self, hub: hubs.HubInfo) -> None:
        try:
            data = model.load_hub(hub)
        except Exception as exc:
            data = exc
        self.bridge.hub_loaded.emit(hub.pid, data)

    def _on_hub_loaded(self, pid: int, data) -> None:
        if pid != self.selected:
            return
        hub = self.hubs.get(pid)
        if isinstance(data, Exception):
            if isinstance(data, hubs.AdminError) and data.status == 404 and hub is not None:
                self.no_admin.add(pid)
                self.detail.setText(model.NO_ADMIN_TEXT % (pid, hub.version or "?"))
                self._update_buttons()
            else:
                self.detail.setText("ハブ PID %d の情報を読めませんでした: %s" % (pid, data))
            return
        self.view.load(data["status"], data["transfers"], data["lines"])
        self.detail.setText("ハブ PID %d（ポート %s、バージョン %s）" % (pid, hub.port if hub else "?",
                                                                 data["status"].get("version")))
        self._render_all()
        if hub is not None:
            self.stream = model.EventStream(hub, lambda e, p=pid: self.bridge.event.emit(p, e),
                                            lambda r, p=pid: self.bridge.stream_closed.emit(p, r))
            self.stream.start()

    def _on_event(self, pid: int, event) -> None:
        if pid != self.selected:
            return
        changed = self.view.apply(event)
        if "clients" in changed:
            self._render_clients()
        if "transfers" in changed:
            self._render_transfers()
        if "log" in changed and model.level_passes(event["entry"], self.level.currentText()):
            self.log_text.appendPlainText(model.log_line(event["entry"]))

    def _on_stream_closed(self, pid: int, reason: str) -> None:
        if pid != self.selected:
            return
        self.stream = None
        self.detail.setText("ハブ PID %d との接続が切れました（%s）。" % (pid, reason))
        self.refresh()

    # ---- rendering -------------------------------------------------------------------
    def _render_all(self) -> None:
        self._render_clients()
        self._render_transfers()
        self._render_log()

    def _render_clients(self) -> None:
        clients = self.view.clients
        _fill(self.client_table, [model.client_row(c) for c in clients], [c.get("client_id") for c in clients])
        self.tabs.setTabText(0, "接続中のアプリ（%d）" % len(clients))
        self._update_buttons()

    def _render_transfers(self) -> None:
        items = list(reversed(self.view.transfer_list()))         # newest first
        _fill(self.transfer_table, [model.transfer_row(i) for i in items])

    def _render_log(self) -> None:
        minimum = self.level.currentText()
        self.log_text.setPlainText("\n".join(model.log_line(e) for e in self.view.log
                                             if model.level_passes(e, minimum)))
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def _update_buttons(self) -> None:
        hub = self.hubs.get(self.selected) if self.selected is not None else None
        running = (hub is not None and hub.state == hubs.RUNNING and bool(hub.token)
                   and hub.pid not in self.no_admin)
        self.stop_btn.setEnabled(running)
        self.kill_btn.setEnabled(hub is not None and hub.alive and hub.verified)
        self.kill_btn.setToolTip("" if hub is None or hub.verified or not hub.alive else
                                 "このプロセスが SyncBridge のハブだと確認できないため、強制終了できません。")
        self.clean_btn.setEnabled(hub is not None and hub.state == hubs.STALE)
        self.disconnect_btn.setEnabled(running and bool(self.client_table.selectionModel().selectedRows()))

    # ---- actions ---------------------------------------------------------------------
    def _confirm(self, title: str, text: str) -> bool:
        return QMessageBox.question(self, title, text, QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No) == QMessageBox.Yes

    def _selected_hub(self) -> Optional[hubs.HubInfo]:
        return self.hubs.get(self.selected) if self.selected is not None else None

    def _stop_hub(self) -> None:
        hub = self._selected_hub()
        if hub is None:
            return
        n = len(self.view.clients)
        if not self._confirm("ハブを停止", "ハブ PID %d（ポート %s）を停止しますか？\n\n接続中のアプリ %d 個は切断されます。"
                             "アプリから再び接続すると、新しいハブが起動します。" % (hub.pid, hub.port, n)):
            return
        _run(self._do, "stop", lambda: hubs.admin_call(hub, "POST", "shutdown"))

    def _kill_hub(self) -> None:
        hub = self._selected_hub()
        if hub is None:
            return
        reason = {hubs.RUNNING: "このハブは応答しています。通常は「停止」を使ってください。",
                  hubs.NOT_RESPONDING: "このハブは応答しません。",
                  hubs.UNKNOWN: "このハブにはセッションファイルがありません。"}.get(hub.state, "")
        if not self._confirm("ハブを強制終了", "%s\n\nプロセスを強制終了しますか？\n\nPID: %d\n実行ファイル: %s\n\n"
                             "転送中だった場合、その転送は完了しません。" % (reason, hub.pid, hub.image or "?")):
            return
        _run(self._do, "kill", lambda: hubs.force_kill(hub))

    def _clean_hub(self) -> None:
        hub = self._selected_hub()
        if hub is None:
            return
        if not self._confirm("ファイルを片付け", "停止済みのハブ PID %d のセッションファイルを削除しますか？\n\n%s"
                             % (hub.pid, hub.file or "")):
            return
        _run(self._do, "clean", lambda: hubs.remove_stale(hub))

    def _disconnect_client(self) -> None:
        hub = self._selected_hub()
        rows = self.client_table.selectionModel().selectedRows()
        if hub is None or not rows:
            return
        client_id = self.client_table.item(rows[0].row(), 0).data(Qt.UserRole)
        if not self._confirm("アプリを切断", "%s をハブから切断しますか？\n\nアプリのパネルから再び接続できます。" % client_id):
            return
        _run(self._do, "disconnect", lambda: hubs.admin_call(hub, "POST", "clients/%s/disconnect" % client_id))

    def _do(self, what: str, fn) -> None:
        try:
            fn()
            error = None
        except Exception as exc:
            error = exc
        self.bridge.action_done.emit(what, error)

    def _on_action_done(self, what: str, error) -> None:
        labels = {"stop": "停止", "kill": "強制終了", "clean": "片付け", "disconnect": "切断"}
        if error is not None:
            QMessageBox.warning(self, TITLE, "%sできませんでした。\n\n%s" % (labels.get(what, what), error))
        else:
            self.statusBar().showMessage("%sしました。" % labels.get(what, what))
        QTimer.singleShot(1000, self.refresh)

    def _open_logs(self) -> None:
        folder = session.logs_dir()
        os.makedirs(folder, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)
        else:
            QMessageBox.information(self, TITLE, folder)

    def closeEvent(self, event) -> None:
        if self.stream is not None:
            self.stream.stop()
        super().closeEvent(event)


def hubs_now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def run(argv=None) -> int:
    app = QApplication.instance() or QApplication(list(argv) if argv is not None else sys.argv)
    window = MonitorWindow()
    window.show()
    return app.exec()
