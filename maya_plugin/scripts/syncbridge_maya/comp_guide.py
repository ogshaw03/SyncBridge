"""Show the AE comp's frame in the active Maya view (D-16).

    show({"name": "main", "width": 1920, "height": 1080, "pixelAspect": 1.0})
    clear()

show() loads plug-ins/syncbridge_guide.py, replaces any earlier guide with one
syncBridgeCompGuide node for the camera of the active view and returns
{status, camera, render, comp, warnings}. Must run on Maya's main thread.

The guide sits in the world (hidden in the Outliner) and is linked to its camera by
cameraShape.worldMatrix[0] -> guide.cameraMatrix: Maya 2023 never drew a plug-in draw
override parented under the camera being looked through (2026-10-16).

The guide is a display aid, not scene data, and is kept out of both the saved file and
the undo history (Maya 2024, checked with mayapy):
  * the nodes are "do not write" (setDoNotWrite), so they are never saved;
  * Maya still writes `requires "syncbridge_guide.py"` while a guide exists, so the plug-in
    takes the guides out just before each save and puts them back right after
    (take_out_for_save / put_back_after_save);
  * creating and deleting guides is not recorded for undo. When the creation was in the undo
    history, deleting and re-creating the guide around a save and then undoing crashed Maya
    2024 (TsetAttrCmd::undoIt). "枠を消す" in the panel (clear()) removes it instead.

Not yet run in Maya: H-MY-21 (playblast -activeEditor names the active model editor).
"""
from __future__ import annotations

import contextlib
import os
from typing import List, Optional

from maya import cmds

from syncbridge.core import comp_guide as core

PLUGIN_FILE = "syncbridge_guide.py"
NODE_TYPE = "syncBridgeCompGuide"
GUIDE_NAME = "syncBridgeCompGuide"

# A size typed in the Maya panel (the AE project may have no comp of the final size).
PRESETS = [
    (u"HD", 1920, 1080),
    (u"UHD 4K", 3840, 2160),
    (u"2K DCI", 2048, 1080),
    (u"4K DCI", 4096, 2160),
    (u"HD 720", 1280, 720),
    (u"縦 HD", 1080, 1920),
    (u"正方形", 1080, 1080),
]
SIZE_OPTION_VAR = "syncBridgeGuideSize"      # the last size typed, "1920 1080"
DEFAULT_SIZE = (1920, 1080)


def plugin_path() -> str:
    """maya_plugin/plug-ins next to scripts/ (repository and install layout)."""
    here = os.path.dirname(os.path.abspath(__file__))                    # scripts/syncbridge_maya
    return os.path.join(os.path.dirname(os.path.dirname(here)), "plug-ins", PLUGIN_FILE)


def ensure_plugin() -> None:
    path = plugin_path()
    if not os.path.isfile(path):
        raise RuntimeError(u"枠を描くプラグインが見つかりません: %s" % path)
    if not cmds.pluginInfo(PLUGIN_FILE, q=True, loaded=True):
        cmds.loadPlugin(path, quiet=True)
    # loadPlugin does not raise when the plug-in's code fails (Maya 2024), and createNode would
    # then make an "unknown" node: check that the node type is really there.
    types = []
    if cmds.pluginInfo(PLUGIN_FILE, q=True, loaded=True):
        types = cmds.pluginInfo(PLUGIN_FILE, q=True, dependNode=True) or []
    if NODE_TYPE not in types:
        raise RuntimeError(u"枠を描くプラグインを読み込めませんでした（%s）。スクリプトエディタのエラーを確認してください。" % path)


def active_camera() -> str:
    """Transform of the camera in the active model panel (or the first visible one)."""
    editors: List[str] = []
    try:
        active = cmds.playblast(activeEditor=True)          # H-MY-21
        if active:
            editors.append(active.split("|")[-1])
    except RuntimeError:
        pass
    focus = cmds.getPanel(withFocus=True)
    if focus and cmds.getPanel(typeOf=focus) == "modelPanel":
        editors.append(focus)
    for panel in cmds.getPanel(visiblePanels=True) or []:
        if cmds.getPanel(typeOf=panel) == "modelPanel":
            editors.append(panel)
    for editor in editors:
        try:
            camera = cmds.modelEditor(editor, q=True, camera=True)
        except RuntimeError:
            continue
        if camera:
            return _camera_transform(camera)
    raise RuntimeError(u"カメラのビューが見つかりません。Maya でビューポートを 1 つ開いてください。")


def _camera_transform(camera: str) -> str:
    if cmds.nodeType(camera) == "camera":
        camera = cmds.listRelatives(camera, parent=True, fullPath=True)[0]
    return cmds.ls(camera, long=True)[0]


def _camera_shape(transform: str) -> str:
    shapes = cmds.listRelatives(transform, shapes=True, type="camera", fullPath=True) or []
    if not shapes:
        raise RuntimeError(u"%s はカメラではありません。" % transform)
    return shapes[0]


def camera_values(shape: str) -> dict:
    g = lambda attr: cmds.getAttr("%s.%s" % (shape, attr))       # noqa: E731
    return {
        "orthographic": bool(g("orthographic")), "orthographic_width": g("orthographicWidth"),
        "focal_length": g("focalLength"), "h_aperture": g("horizontalFilmAperture"),
        "v_aperture": g("verticalFilmAperture"), "h_offset": g("horizontalFilmOffset"),
        "v_offset": g("verticalFilmOffset"), "film_fit": g("filmFit"),
        "lens_squeeze": g("lensSqueezeRatio"), "camera_scale": g("cameraScale"),
        "pre_scale": g("preScale"), "post_scale": g("postScale"),
        "film_translate_h": g("filmTranslateH"), "film_translate_v": g("filmTranslateV"),
    }


def render_values() -> dict:
    return {"width": cmds.getAttr("defaultResolution.width"),
            "height": cmds.getAttr("defaultResolution.height"),
            "device_aspect": cmds.getAttr("defaultResolution.deviceAspectRatio"),
            "pixel_aspect": cmds.getAttr("defaultResolution.pixelAspect")}


def guide_camera(shape: str) -> Optional[str]:
    """The camera transform a guide is linked to, or None."""
    sources = cmds.listConnections(shape + ".cameraMatrix", source=True, destination=False, shapes=True) or []
    if not sources:
        return None
    return _camera_transform(sources[0])


def existing() -> List[str]:
    """Guide shapes in the scene (the plug-in may not be loaded yet)."""
    try:
        return cmds.ls(type=NODE_TYPE, long=True) or []
    except RuntimeError:
        return []


@contextlib.contextmanager
def _not_recorded_for_undo():
    """Run without adding to the undo history; the user's earlier history is kept."""
    was_on = cmds.undoInfo(q=True, state=True)
    cmds.undoInfo(stateWithoutFlush=False)
    try:
        yield
    finally:
        cmds.undoInfo(stateWithoutFlush=was_on)


def _delete(shapes: List[str]) -> int:
    transforms = []
    for shape in shapes:
        parent = cmds.listRelatives(shape, parent=True, fullPath=True)
        transforms.append(parent[0] if parent else shape)
    if transforms:
        cmds.delete(transforms)
    return len(transforms)


def _do_not_write(node: str) -> None:
    import maya.api.OpenMaya as om
    sel = om.MSelectionList()
    sel.add(node)
    om.MFnDependencyNode(sel.getDependNode(0)).setDoNotWrite(True)


def _create(camera: str, width: int, height: int, name: str, line_width: Optional[float] = None) -> str:
    shape = _camera_shape(camera)
    transform = None
    try:
        transform = cmds.createNode("transform", name=GUIDE_NAME, skipSelect=True)
        transform = cmds.ls(transform, long=True)[0]
        guide = cmds.createNode(NODE_TYPE, name=GUIDE_NAME + "Shape", parent=transform, skipSelect=True)
        guide = cmds.ls(guide, long=True)[0]
        cmds.connectAttr(shape + ".worldMatrix[0]", guide + ".cameraMatrix")
        if cmds.attributeQuery("hiddenInOutliner", node=transform, exists=True):
            cmds.setAttr(transform + ".hiddenInOutliner", True)
        cmds.setAttr(guide + ".compWidth", width)
        cmds.setAttr(guide + ".compHeight", height)
        cmds.setAttr(guide + ".compName", name, type="string")
        if line_width is not None:
            cmds.setAttr(guide + ".lineWidth", line_width)
        for attr in ("translate", "rotate", "scale"):
            cmds.setAttr("%s.%s" % (transform, attr), lock=True)
        for node in (transform, guide):
            _do_not_write(node)
    except Exception:
        if transform and cmds.objExists(transform):     # leave nothing half made behind
            cmds.delete(transform)
        raise
    return guide


def show(comp_data: dict, camera: Optional[str] = None) -> dict:
    comp = core.parse_comp(comp_data)
    ensure_plugin()
    camera = _camera_transform(camera) if camera else active_camera()
    shape = _camera_shape(camera)
    render = render_values()
    warnings = core.warnings(camera_values(shape), render, comp)
    with _not_recorded_for_undo():
        _delete(existing())
        _create(camera, comp["width"], comp["height"], comp["name"])
    return {"status": "applied", "camera": camera.split("|")[-1],
            "render": [render["width"], render["height"]], "comp": [comp["width"], comp["height"]],
            "warnings": warnings}


def last_size() -> tuple:
    """The size last typed in the panel (Maya preference), or 1920x1080."""
    try:
        if cmds.optionVar(exists=SIZE_OPTION_VAR):
            width, height = (int(v) for v in str(cmds.optionVar(q=SIZE_OPTION_VAR)).split())
            if width > 0 and height > 0:
                return width, height
    except (ValueError, RuntimeError):
        pass
    return DEFAULT_SIZE


def show_size(width: int, height: int, camera: Optional[str] = None) -> dict:
    """Show a frame of a size typed in the Maya panel; remembers the size for next time."""
    result = show({"name": "", "width": width, "height": height}, camera=camera)
    cmds.optionVar(stringValue=(SIZE_OPTION_VAR, "%d %d" % (int(width), int(height))))
    return result


def clear() -> int:
    """Delete every comp guide. Returns how many were removed."""
    shapes = existing()
    if not shapes:
        return 0
    with _not_recorded_for_undo():
        return _delete(shapes)


def take_out_for_save() -> List[dict]:
    """Called by the plug-in before a save: remove every guide, return what puts them back."""
    stash = []
    for shape in existing():
        camera = guide_camera(shape)
        if camera is None:
            continue
        stash.append({"camera": camera, "width": cmds.getAttr(shape + ".compWidth"),
                      "height": cmds.getAttr(shape + ".compHeight"),
                      "name": cmds.getAttr(shape + ".compName") or "",
                      "line_width": cmds.getAttr(shape + ".lineWidth")})
    if stash:
        with _not_recorded_for_undo():
            _delete(existing())
    return stash


def put_back_after_save(stash: List[dict]) -> None:
    """Called by the plug-in after a save."""
    if not stash:
        return
    with _not_recorded_for_undo():
        for item in stash:
            if cmds.objExists(item["camera"]):
                _create(item["camera"], item["width"], item["height"], item["name"], item["line_width"])
