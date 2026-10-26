"""Phase 3 (D-30) from a window: range dialog -> AE asked link by link -> solve -> one confirmation ->
keys in one undo. Shared by the layer map and the viewer (the layer map is not always open, the user,
2026-10-25).

    transfer = MotionTransfer(window, window.say)
    transfer.all()                 # every link
    transfer.layer(layer_id)       # the links of one Maya layer
    transfer.link(mapping_id)      # one link
"""
from __future__ import annotations

try:
    from PySide6 import QtWidgets
except ImportError:
    from PySide2 import QtWidgets

from syncbridge.core import layer_mapping as core_lm

from . import layer_mapping, service

NOT_CONNECTED = u"SyncBridge のサーバーに接続していません。SyncBridge のパネルで Connect を押してください。"


def camera_label(path) -> str:
    from .motion import camera_label as label
    return label(path)


def with_warnings(text: str, warnings) -> str:
    return text + "".join(u"\n注意: %s" % w for w in warnings or [])


class MotionDialog(QtWidgets.QDialog):
    """The Maya frame range to key (Maya's playback range by default). The Origin frame is the tool's one
    value (D-38), shown, not asked."""

    def __init__(self, text: str, start: float, end: float, origin: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle(u"SyncBridge - アニメーションを転送")
        self.setMinimumWidth(460)
        self._origin = float(origin)
        self.start, self.end = QtWidgets.QDoubleSpinBox(), QtWidgets.QDoubleSpinBox()
        for box, value in ((self.start, start), (self.end, end)):
            box.setRange(-1e6, 1e6)
            box.setDecimals(0)
            box.setValue(value)
        form = QtWidgets.QFormLayout()
        form.addRow(u"開始フレーム", self.start)
        form.addRow(u"終了フレーム", self.end)
        form.addRow(u"Origin frame", QtWidgets.QLabel(u"%g（パネルと AE で共通。変えるときはパネルで）" % self._origin))
        text = QtWidgets.QLabel(text + u"\n範囲は Maya の再生範囲が入っています。Origin frame は AE のコンプの 0 秒にあたる Maya のフレームです。")
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
        return self.start.value(), self.end.value(), self._origin


class MotionTransfer(object):
    """`parent` owns the dialogs; `say(text, error=False)` shows the outcome."""

    def __init__(self, parent, say):
        self.parent = parent
        self.say = say

    def link(self, mapping_id: str):
        """One link (the selected wire)."""
        link = next((m for m in layer_mapping.stored() if m["id"] == mapping_id), None)
        if link is not None:
            self._transfer([link], [], u"AE のレイヤー「%s」の動きを、範囲の各フレームのキーとしてカメラ %s に打ちます。"
                           % (link["ae"].get("layer"), camera_label(link["maya"].get("camera"))))

    def all(self):
        """Every link: one range, AE asked link by link, one confirmation, one undo."""
        from . import motion
        links, skipped = motion.transferable(layer_mapping.store())
        self._many(links, skipped, u"転送できる接続がありません。")

    def layer(self, layer_id: str):
        """The links of one Maya layer (the viewer's layer list)."""
        from . import motion
        store = layer_mapping.store()
        layer = core_lm.maya_layer(store, layer_id)
        if layer is None:
            return
        mine = dict(store, mappings=core_lm.links_of(store, layer_id))
        links, skipped = motion.transferable(mine)
        self._many(links, skipped, u"Maya レイヤー「%s」には転送できる接続がありません（レイヤーマップで AE のレイヤーとつないでください）。"
                   % layer["name"])

    def _many(self, links, skipped, none_text):
        if not links:
            self.say(none_text + u" ".join(skipped), error=True)
            return
        if len(links) == 1 and not skipped:
            self.link(links[0]["id"])
            return
        text = u"%d 本の接続の AE の動きを、範囲の各フレームのキーとしてそれぞれのカメラに打ちます。" % len(links)
        if skipped:
            text += u"（%d 本は打ちません: 確認の画面に理由が出ます）" % len(skipped)
        self._transfer(links, skipped, text)

    def _transfer(self, links, skipped, text):
        """Range dialog -> ask AE for each link's layer at every frame -> solve -> confirm -> keys."""
        from . import motion, timing
        if not service.is_connected():
            self.say(NOT_CONNECTED, error=True)
            return
        start, end = timing.playback_range()
        store = layer_mapping.store()
        outside = [link["ae"].get("layer") for link in links if core_lm.outside_main(store, link["ae"])]
        if outside:
            text += (u"\n⚠ メインのコンポの外で記録された接続があります（%s）。メインのコンポでの動き（プリコンポを動かした"
                     u"カメラワークなど）は入りません。レイヤーマップでメインのコンポを開いて「AE のレイヤーを読み込む」を押すと直せます。"
                     % u"、".join(outside))
        dialog = MotionDialog(text, start, end, timing.origin(), self.parent)
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
                self._finish(plans, skipped, len(links) == 1)
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

    def _finish(self, plans, skipped, single):
        from . import motion
        if not plans:
            self.say(u"アニメーションを転送できませんでした（カメラは変えていません）: " + u" / ".join(skipped), error=True)
            return
        try:
            results = motion.apply_all(plans, parent=self.parent, skipped=[] if single else skipped)
        except Exception as exc:
            self.say(u"アニメーションを転送できませんでした（カメラは変えていません）: %s" % exc, error=True)
            return
        if results[0]["status"] == "cancelled":
            self.say(u"アニメーションの転送はキャンセルしました（カメラは変えていません）。")
            return
        bad = [r for r in results if not r["readback"]["passed"]]
        lines = [u"%s → %s（%s、誤差 最大 %.3f px）" % (r["ae_layer"], camera_label(r["camera"]), ", ".join(r["attrs"]),
                                                    r["max_error_px"]) for r in results]
        warnings = []
        for r in results:
            warnings += [w for w in r["warnings"] if w not in warnings]
        text = u"%g〜%g フレームのキーを打ちました（読み戻し %s）。元に戻すときは Ctrl+Z を 1 回。\n%s" % (
            results[0]["frames"][0], results[0]["frames"][1],
            u"一致" if not bad else u"不一致 %d 本" % len(bad), u"\n".join(lines))
        if skipped and not single:
            text += u"\n打たなかったもの: " + u" / ".join(skipped)
        self.say(with_warnings(text, warnings), error=bool(bad))
        service.announce("layer_map")
