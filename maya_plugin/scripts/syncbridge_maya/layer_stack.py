"""The layer stack view (D-32, prototype): one view draws the Maya layers on top of each other, each
through its own camera, like AE layers (plug-ins/syncbridge_layer_stack.py).

    layer_stack.enable()            the focused view (or the first visible one) shows the stack
    layer_stack.disable()           back to Viewport 2.0
    layer_stack.publish()           hand the scene's layers to the plug-in (after a change)

Only the views change; nothing in the scene does.
"""
from __future__ import annotations

import os
from typing import List, Optional

from maya import cmds

from syncbridge.core import layer_mapping as core_lm

from . import layer_mapping

PLUGIN_FILE = "syncbridge_layer_stack.py"
OVERRIDE_NAME = "SyncBridgeLayerStack"           # plug-in's OVERRIDE_NAME
STATE_KEY = "_syncbridge_layer_stack"            # plug-in's STATE_KEY


def plugin_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(os.path.dirname(here)), "plug-ins", PLUGIN_FILE)


def ensure_plugin() -> None:
    path = plugin_path()
    if not os.path.isfile(path):
        raise RuntimeError(u"重ねて表示するプラグインが見つかりません: %s" % path)
    if not cmds.pluginInfo(PLUGIN_FILE, q=True, loaded=True):
        cmds.loadPlugin(path, quiet=True)
    if not cmds.pluginInfo(PLUGIN_FILE, q=True, loaded=True):
        raise RuntimeError(u"重ねて表示するプラグインを読み込めませんでした（%s）。スクリプトエディタのエラーを確認してください。" % path)


def layers() -> List[tuple]:
    """[(name, camera path, [object paths])] bottom first, nodes that are gone left out."""
    return _resolve(core_lm.stack(layer_mapping.store()))


def _resolve(stack):
    out = []
    for item in stack:
        camera = layer_mapping.node_by_uuid(item["camera_uuid"])
        objects = [p for p in (layer_mapping.node_by_uuid(u) for u in item["object_uuids"]) if p]
        if camera and objects:
            out.append((item["name"], camera, objects))
    return out


def view_camera(store: Optional[dict] = None) -> Optional[str]:
    """The camera the viewer looks through and draws the comp frame for (core view_camera_uuid)."""
    return layer_mapping.node_by_uuid(core_lm.view_camera_uuid(store or layer_mapping.store()))


def frame_overlay(camera: Optional[str]) -> Optional[tuple]:
    """(camera, {width, height, name}) of the AE comp frame (D-16) shown for this camera, which the
    plug-in draws over the stack (Maya's resolution gate would turn the overscan to 1.3, D-27).
    The comp guide node is only read: inside the stack its own drawing is never called (the user saw
    no frame, 2026-10-25), so the plug-in draws the same frame with syncbridge.core.comp_guide."""
    from . import comp_guide
    if not camera:
        return None
    camera_tr = cmds.listRelatives(camera, parent=True, fullPath=True)[0] if cmds.nodeType(camera) == "camera" \
        else camera
    guides = comp_guide.existing()
    # the camera's own frame first; else the frame shown on another camera (the same AE comp: the layers
    # may use different cameras, e.g. a plate camera in the source camera mode, D-39)
    mine = [g for g in guides if comp_guide.guide_camera(g) == camera_tr]
    if not guides:
        return None
    guide = (mine or guides)[0]
    return (camera, {"width": cmds.getAttr(guide + ".compWidth"), "height": cmds.getAttr(guide + ".compHeight"),
                     "name": cmds.getAttr(guide + ".compName") or ""})


def publish() -> List[tuple]:
    """Hand the layers to the plug-in; the views redraw when Maya next draws (no forced refresh: a burst
    of forced refreshes while toggling layers quickly is what crashed Maya, 2026-10-25)."""
    import __main__
    import maya.api.OpenMayaUI as omui2
    old = getattr(__main__, STATE_KEY, None) or {"version": 0, "layers": None}
    store = layer_mapping.store()
    stack = _resolve(core_lm.stack(store))
    overlay = frame_overlay(view_camera(store))
    m, s, e = margin(), shade(), editing()
    if stack != old.get("layers") or overlay != old.get("overlay") or m != old.get("margin") \
            or s != old.get("shade") or e != old.get("editing"):
        setattr(__main__, STATE_KEY, {"version": old["version"] + 1, "layers": stack, "overlay": overlay,
                                      "margin": m, "shade": s, "editing": e})
        omui2.M3dView.scheduleRefreshAllViews()
    return stack


def editing() -> Optional[tuple]:
    """(dedicated camera, viewer camera) of the layer edited in the viewer (D-44), or None: the viewer
    camera is the only record of it (it is a child of that layer's dedicated camera)."""
    from . import viewer_camera
    shape = viewer_camera.current()
    if not shape:
        return None
    dedicated = viewer_camera.followed(shape)
    return (dedicated, shape) if dedicated else None


MARGIN_VAR = "syncBridgeViewerMargin"          # optionVar: 1.0 = none, 1.2 = 20 %
DEFAULT_MARGIN = 1.2


def margin() -> float:
    """How much the viewer zooms out while the comp frame is shown (D-35)."""
    if cmds.optionVar(exists=MARGIN_VAR):
        try:
            return max(1.0, float(cmds.optionVar(q=MARGIN_VAR)))
        except (TypeError, ValueError):
            pass
    return DEFAULT_MARGIN


def set_margin(value: float) -> None:
    cmds.optionVar(floatValue=(MARGIN_VAR, max(1.0, float(value))))
    publish()


SHADE_VAR = "syncBridgeViewerShade"            # optionVar: opacity of the black outside the comp frame
DEFAULT_SHADE = 0.5                            # the plug-in's DEFAULT_SHADE


def shade() -> float:
    """How dark the view is outside the comp frame: 0 = not darkened, 1 = black (the user, 2026-10-27)."""
    if cmds.optionVar(exists=SHADE_VAR):
        try:
            return min(1.0, max(0.0, float(cmds.optionVar(q=SHADE_VAR))))
        except (TypeError, ValueError):
            pass
    return DEFAULT_SHADE


def set_shade(value: float) -> None:
    cmds.optionVar(floatValue=(SHADE_VAR, min(1.0, max(0.0, float(value)))))
    publish()


def _panel(panel: Optional[str]) -> str:
    from .layer_view import view_panel
    return panel or view_panel()


def enabled_panels() -> List[str]:
    out = []
    for panel in cmds.getPanel(type="modelPanel") or []:
        try:
            if cmds.modelEditor(panel, q=True, rendererOverrideName=True) == OVERRIDE_NAME:
                out.append(panel)
        except RuntimeError:
            pass
    return out


def enable(panel: Optional[str] = None) -> dict:
    ensure_plugin()
    panel = _panel(panel)
    stack = publish()
    if not stack:
        raise ValueError(u"重ねるレイヤーがありません（カメラと表示するオブジェクトのある Maya レイヤーが要ります）。")
    cmds.modelEditor(panel, e=True, rendererName="vp2Renderer", rendererOverrideName=OVERRIDE_NAME)
    return {"panel": panel, "layers": [name for name, _, _ in stack]}


def disable(panel: Optional[str] = None) -> str:
    panel = _panel(panel)
    cmds.modelEditor(panel, e=True, rendererOverrideName="")
    return panel
