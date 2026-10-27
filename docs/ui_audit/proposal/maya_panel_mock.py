"""Mock of a reorganised SyncBridge panel for Maya (tabs). Not the product code: for the user to judge."""
import glob
import os
import sys

from PySide6 import QtCore, QtGui, QtWidgets

OUT = sys.argv[1]
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
app = QtWidgets.QApplication(sys.argv)
app.setStyle("Fusion")
pal = QtGui.QPalette()
for role, color in ((QtGui.QPalette.Window, "#444444"), (QtGui.QPalette.WindowText, "#dddddd"),
                    (QtGui.QPalette.Base, "#2b2b2b"), (QtGui.QPalette.AlternateBase, "#383838"),
                    (QtGui.QPalette.Text, "#dddddd"), (QtGui.QPalette.Button, "#5d5d5d"),
                    (QtGui.QPalette.ButtonText, "#eeeeee"), (QtGui.QPalette.Highlight, "#5285a6")):
    pal.setColor(role, QtGui.QColor(color))
for role in (QtGui.QPalette.ButtonText, QtGui.QPalette.WindowText, QtGui.QPalette.Text):
    pal.setColor(QtGui.QPalette.Disabled, role, QtGui.QColor("#7a7a7a"))
app.setPalette(pal)
app.setFont(QtGui.QFont("Yu Gothic UI", 9))

GREEN, GREY, ORANGE = "#5cc85c", "#7a7a7a", "#e0a030"
LOGO = (glob.glob(os.path.join(ROOT, "maya_plugin", "icons", "syncbridge*.png")) or [None])[0]


def dot(text, on, color=None):
    w = QtWidgets.QLabel(u"<span style='color:%s'>●</span> %s" % (color or (GREEN if on else GREY), text))
    return w


def group(title, *widgets):
    box = QtWidgets.QGroupBox(title)
    lay = QtWidgets.QVBoxLayout(box)
    lay.setSpacing(6)
    for w in widgets:
        if isinstance(w, QtWidgets.QLayout):
            lay.addLayout(w)
        else:
            lay.addWidget(w)
    return box


def row(*widgets, stretch_first=False):
    h = QtWidgets.QHBoxLayout()
    for i, w in enumerate(widgets):
        if w is None:
            h.addStretch(1)
        elif isinstance(w, QtWidgets.QLayout):
            h.addLayout(w)
        else:
            h.addWidget(w, 1 if (stretch_first and i == 0) else 0)
    return h


def button(text, primary=False, tip=""):
    b = QtWidgets.QPushButton(text)
    b.setMinimumHeight(30 if primary else 24)
    if primary:
        b.setStyleSheet("QPushButton { background: #3f6d8f; font-weight: bold; } "
                        "QPushButton:disabled { background: #4a4a4a; }")
    if tip:
        b.setToolTip(tip)
    return b


def note(text):
    lab = QtWidgets.QLabel(text)
    lab.setWordWrap(True)
    lab.setStyleSheet("color: #a8a8a8;")
    return lab


def check(text, on=False, color=None):
    c = QtWidgets.QCheckBox(text)
    c.setChecked(on)
    if on and color:
        c.setStyleSheet("QCheckBox { color: %s; font-weight: bold; }" % color)
    return c


def build(tab_index):
    w = QtWidgets.QDialog()
    w.setWindowTitle("SyncBridge 0.1.10")
    lay = QtWidgets.QVBoxLayout(w)
    lay.setSpacing(6)

    # (1) connection and state: one look tells what is connected and what is on
    head = QtWidgets.QHBoxLayout()
    if LOGO:
        logo = QtWidgets.QLabel()
        logo.setPixmap(QtGui.QPixmap(LOGO).scaled(28, 28, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
        head.addWidget(logo)
    title = QtWidgets.QLabel("<b>SyncBridge</b> <span style='color:#9a9a9a'>0.1.10</span>")
    head.addWidget(title, 1)
    head.addWidget(button(u"切断"))
    lay.addLayout(head)
    state = QtWidgets.QFrame()
    state.setStyleSheet("QFrame { background: #3a3a3a; border-radius: 4px; }")
    grid = QtWidgets.QGridLayout(state)
    grid.setContentsMargins(8, 6, 8, 6)
    grid.addWidget(dot(u"サーバー: 接続中", True), 0, 0)
    grid.addWidget(dot(u"After Effects: 接続中（shot010.aep）", True), 0, 1)
    grid.addWidget(dot(u"タイムスライダー同期: オン", True), 1, 0)
    grid.addWidget(dot(u"リアルタイム同期: オフ", False), 1, 1)
    lay.addWidget(state)
    origin = QtWidgets.QDoubleSpinBox()
    origin.setDecimals(0)
    origin.setRange(-1e6, 1e6)
    origin.setValue(1001)
    origin.setToolTip(u"AE のコンポの 0 秒にあたる Maya のフレーム。シーンに保存され、AE のパネルとも共通")
    origin_note = QtWidgets.QLabel(u"＝ AE のコンポの 0 秒（AE と共通）")
    origin_note.setStyleSheet("color: #a8a8a8;")
    lay.addLayout(row(QtWidgets.QLabel(u"Origin frame"), origin, origin_note, None))

    tabs = QtWidgets.QTabWidget()
    tabs.setStyleSheet("QTabWidget::pane { background: #3d3d3d; border: 1px solid #2a2a2a; top: -1px; }"
                       "QTabBar::tab { padding: 5px 12px; }"
                       "QTabBar::tab:selected { background: #3d3d3d; font-weight: bold; }")
    # -- tab: time warp
    t1 = QtWidgets.QWidget()
    v = QtWidgets.QVBoxLayout(t1)
    v.addWidget(note(u"Maya の Scene Time Warp ⇔ AE で選んでいるレイヤーのタイムリマップ"))
    v.addWidget(group(u"転送",
                      row(button(u"タイムワープを AE へ  →", True), button(u"←  AE から読み込む", True)),
                      note(u"AE: shot010 / BG_pre（選択中）")))
    v.addWidget(group(u"Scene Time Warp",
                      row(button(u"保存"), button(u"復元…"), button(u"範囲変更…"))))
    detail = QtWidgets.QToolButton()
    detail.setText(u"▸ 詳細（モード: editable、許容誤差: 0.1 フレーム）")
    detail.setStyleSheet("QToolButton { border: none; color: #9a9a9a; }")
    v.addWidget(detail)
    v.addStretch(1)
    tabs.addTab(t1, u"タイムワープ")
    # -- tab: sync and scene settings
    t2 = QtWidgets.QWidget()
    v = QtWidgets.QVBoxLayout(t2)
    v.addWidget(group(u"タイムスライダー",
                      row(check(u"同期する", True, GREEN), check(u"再生中も追従"), None),
                      note(u"Maya と AE のどちらで時間を動かしても、もう片方が合わせます（AE のパネルと共通）")))
    checks = QtWidgets.QGridLayout()
    for i, t in enumerate((u"FPS", u"再生範囲", u"アニメーション範囲", u"ピクセル縦横比")):
        c = QtWidgets.QCheckBox(t)
        c.setChecked(True)
        checks.addWidget(c, i // 2, i % 2)
    v.addWidget(group(u"シーン設定", checks,
                      row(button(u"Maya の設定を AE へ  →"), button(u"←  AE の設定を Maya へ")),
                      note(u"受け取る側で確認してから適用します")))
    v.addStretch(1)
    tabs.addTab(t2, u"同期・設定")
    # -- tab: layers (BG slide)
    t3 = QtWidgets.QWidget()
    v = QtWidgets.QVBoxLayout(t3)
    summary = QtWidgets.QLabel(u"接続 3 本（Maya レイヤー 3）　<span style='color:%s'>基準なし 0</span>" % GREEN)
    v.addWidget(group(u"レイヤー（BG スライド・カメラワーク）", summary,
                      row(button(u"レイヤーマップ", True), button(u"ビューアー", True))))
    v.addWidget(group(u"AE の動きを Maya へ",
                      check(u"リアルタイム同期（AE で変え終えたら自動で反映）"),
                      button(u"すべてのアニメーションを転送…"),
                      note(u"つないだレイヤーの動きを、各 Maya レイヤーの専用カメラのキーにします")))
    v.addStretch(1)
    tabs.addTab(t3, u"レイヤー")
    # -- tab: other tools
    t4 = QtWidgets.QWidget()
    v = QtWidgets.QVBoxLayout(t4)
    wsp, hsp = QtWidgets.QSpinBox(), QtWidgets.QSpinBox()
    for s, val in ((wsp, 1920), (hsp, 1080)):
        s.setRange(1, 32768)
        s.setValue(val)
    preset = QtWidgets.QComboBox()
    preset.addItems([u"プリセット…", "HD 1920 x 1080"])
    v.addWidget(group(u"解像度の枠",
                      row(QtWidgets.QLabel(u"幅"), wsp, QtWidgets.QLabel(u"高さ"), hsp, preset),
                      row(None, button(u"枠を表示"), button(u"枠を消す")),
                      note(u"AE のパネルの「解像度の枠を Maya へ」でも出せます")))
    v.addWidget(group(u"AE のキーのマーカー",
                      row(QtWidgets.QLabel(u"マーカー 6 個（BG_pre）"), None, button(u"マーカーを消す"))))
    v.addStretch(1)
    tabs.addTab(t4, u"その他")
    tabs.setCurrentIndex(tab_index)
    lay.addWidget(tabs, 3)

    log = QtWidgets.QPlainTextEdit()
    log.setReadOnly(True)
    log.setPlainText(u"10:12:03  サーバーに接続しました（ID maya-1）\n"
                     u"10:12:04  After Effects がつながりました\n"
                     u"10:15:40  タイムワープを AE へ送りました: 適用（変換の誤差 0.000 フレーム）")
    log.setMaximumHeight(110)
    lay.addWidget(log, 1)
    return w


names = ["timewarp", "sync", "layers", "other"]
for i, n in enumerate(names):
    w = build(i)
    w.resize(440, 600)
    w.show()
    app.processEvents()
    w.grab().save(os.path.join(OUT, "proposal_maya_%d_%s.png" % (i + 1, n)))
    print("saved", n)

# before / after side by side (the current panel's mock, same height)
before = QtGui.QPixmap(os.path.join(ROOT, "docs", "ui_audit", "w1_maya_panel.png"))
after = QtGui.QPixmap(os.path.join(OUT, "proposal_maya_1_timewarp.png"))
pad, top = 24, 30
img = QtGui.QPixmap(before.width() + after.width() + pad * 3, max(before.height(), after.height()) + top + pad)
img.fill(QtGui.QColor("#202020"))
p = QtGui.QPainter(img)
p.setPen(QtGui.QColor("#e0e0e0"))
p.setFont(QtGui.QFont("Yu Gothic UI", 11, QtGui.QFont.Bold))
p.drawText(pad, 21, u"今（440×820、スクロールあり）")
p.drawText(pad * 2 + before.width(), 21, u"案（440×600、タブ）")
p.drawPixmap(pad, top, before)
p.drawPixmap(pad * 2 + before.width(), top, after)
p.end()
img.save(os.path.join(OUT, "proposal_maya_compare.png"))
print("saved compare")
