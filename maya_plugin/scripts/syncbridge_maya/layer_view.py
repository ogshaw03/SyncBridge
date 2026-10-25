"""Show one Maya layer in a view (D-31): the view looks through the layer's camera (its dedicated
camera, D-29) and shows only the layer's objects (Isolate Select). Nothing in the scene changes; the
view's own state is all that changes (the user's choice: viewport only, 2026-10-25).

    layer_view.show_layer(layer)     -> {panel, camera, shown, missing}
    layer_view.show_all()            Isolate Select off (the camera stays)

H-MY-32: isolateSelect with state 1 and an empty selection shows nothing, then -addDagObject adds a
transform with its children; playblast draws what the view shows.
"""
from __future__ import annotations

from typing import Optional

from maya import cmds

from syncbridge.core import layer_mapping as core_lm

from . import layer_mapping


def view_panel() -> str:
    """The model panel with the focus, else the first visible one."""
    panel = cmds.getPanel(withFocus=True)
    if panel and cmds.getPanel(typeOf=panel) == "modelPanel":
        return panel
    for panel in cmds.getPanel(visiblePanels=True) or []:
        if cmds.getPanel(typeOf=panel) == "modelPanel":
            return panel
    raise ValueError(u"ビュー（モデルパネル）が見つかりません。ビューをクリックしてから、もう一度押してください。")


def _objects(layer: dict):
    found, missing = [], []
    for entry in layer.get("objects") or []:
        node = layer_mapping.node_by_uuid(entry.get("uuid"))
        (found if node else missing).append(node or core_lm.short_name(entry.get("name")))
    return found, missing


def show_layer(layer: dict, panel: Optional[str] = None) -> dict:
    cam = core_lm.driven_camera(layer)
    camera = layer_mapping.node_by_uuid(cam["camera_uuid"])
    if camera is None:
        raise ValueError(u"Maya レイヤー「%s」のカメラがシーンにありません。" % layer["name"])
    objects, missing = _objects(layer)
    if not objects:
        raise ValueError(u"Maya レイヤー「%s」には表示するオブジェクトがありません（右の欄の「選択中を追加」で入れてください）。"
                         % layer["name"])
    panel = panel or view_panel()
    selection = cmds.ls(selection=True, long=True) or []
    cmds.lookThru(panel, camera)
    cmds.select(clear=True)
    try:
        cmds.isolateSelect(panel, state=False)
        cmds.isolateSelect(panel, state=True)          # isolates the (empty) selection
        for node in objects:
            cmds.isolateSelect(panel, addDagObject=node)
    finally:
        if selection:
            cmds.select(selection, replace=True)
    return {"panel": panel, "camera": camera, "shown": objects, "missing": missing}


def show_all(panel: Optional[str] = None) -> str:
    panel = panel or view_panel()
    cmds.isolateSelect(panel, state=False)
    return panel


def isolated(panel: str) -> bool:
    return bool(cmds.isolateSelect(panel, query=True, state=True))
