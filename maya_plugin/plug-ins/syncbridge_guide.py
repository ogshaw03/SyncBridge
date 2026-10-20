"""SyncBridge comp guide: draws the AE comp's frame inside Maya's resolution gate (D-16).

A plug-in shape node (syncBridgeCompGuide; a locator until D-20) in the world, linked to a camera by a connection
    cameraShape.worldMatrix[0] -> syncBridgeCompGuide.cameraMatrix
Viewport 2.0 only; it is never rendered. It draws only in views that look through its
camera. The frame is computed by syncbridge.core.comp_guide from the camera,
defaultResolution and the comp size every time the view is drawn, in camera space, then
moved to the world with the camera's matrix (camera moves and edits are followed).

Why not parented under the camera: Maya 2023 created the draw override of a guide under the
camera being looked through but never asked it to prepare or draw (a plain locator there is
drawn; the same guide in the world is drawn). Checked on the user's PC, 2026-10-16.

Status (docs/PHASE0_RESEARCH.md):
    H-MY-19  MPxLocatorNode + MPxDrawOverride (Python API 2.0) draw in Maya 2023-2025
             (now MPxSurfaceShape + the same draw override, D-20 / H-MY-27)
    H-MY-20  the computed resolution gate matches MFnCamera.getRenderingFrustum (perspective,
             all film fits, mayapy 2024); not yet compared on screen
Node ID 0x0007F5B0 is in the range Autodesk leaves for in-house plug-ins.
"""
from __future__ import annotations

import json
import os
import sys

import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma
import maya.api.OpenMayaRender as omr
import maya.api.OpenMayaUI as omui

comp_guide = None     # syncbridge.core.comp_guide, imported in initializePlugin()
core_markers = None   # syncbridge.core.markers (key markers overlay, D-18)


def _import_core(plugin_dir):
    """The plug-in sits next to the scripts folder: <install>/maya/{plug-ins,scripts/syncbridge}
    in a release, maya_plugin/{plug-ins,scripts} + src/syncbridge in the repository.
    Maya runs this file without __file__ (Maya 2024), so the folder comes from MFnPlugin.loadPath()."""
    global comp_guide, core_markers
    maya_dir = os.path.dirname(os.path.normpath(plugin_dir))
    for path in (os.path.join(maya_dir, "scripts"), os.path.join(os.path.dirname(maya_dir), "src")):
        has_package = any(os.path.isdir(os.path.join(path, p)) for p in ("syncbridge", "syncbridge_maya"))
        if has_package and path not in sys.path:
            sys.path.append(path)
    from syncbridge.core import comp_guide as module
    from syncbridge.core import markers as markers_module
    comp_guide = module
    core_markers = markers_module


NODE_NAME = "syncBridgeCompGuide"
NODE_ID = om.MTypeId(0x0007F5B0)
DRAW_CLASSIFICATION = "drawdb/geometry/syncBridgeCompGuide"
DRAW_REGISTRANT = "SyncBridgeCompGuidePlugin"
COLOR = om.MColor((1.0, 0.55, 0.1, 1.0))


def maya_useNewAPI():
    """Tells Maya this plug-in uses the Python API 2.0."""


class CompGuideNode(om.MPxSurfaceShape):
    comp_width = None
    comp_height = None
    comp_name = None
    line_width = None
    camera_matrix = None

    @staticmethod
    def creator():
        return CompGuideNode()

    @staticmethod
    def initialize():
        num = om.MFnNumericAttribute()
        CompGuideNode.comp_width = num.create("compWidth", "cw", om.MFnNumericData.kInt, 1920)
        num.setMin(1)
        CompGuideNode.comp_height = num.create("compHeight", "ch", om.MFnNumericData.kInt, 1080)
        num.setMin(1)
        CompGuideNode.line_width = num.create("lineWidth", "lw", om.MFnNumericData.kFloat, 2.0)
        num.setMin(0.5)
        typed = om.MFnTypedAttribute()
        CompGuideNode.comp_name = typed.create("compName", "cn", om.MFnData.kString)
        matrix = om.MFnMatrixAttribute()
        # The camera's worldMatrix: says which camera, and moving the camera dirties the guide.
        CompGuideNode.camera_matrix = matrix.create("cameraMatrix", "cm", om.MFnMatrixAttribute.kDouble)
        matrix.storable = False
        for attr in (CompGuideNode.comp_width, CompGuideNode.comp_height, CompGuideNode.line_width,
                     CompGuideNode.comp_name, CompGuideNode.camera_matrix):
            om.MPxNode.addAttribute(attr)

    def excludeAsPluginShape(self):
        return True           # own Show menu item, not "Plugin Shapes" (see DISPLAY_FILTERS)

    def isBounded(self):
        # Unbounded: never culled. The frame moves with the camera, but Viewport 2.0 kept the
        # bounding box from when the guide was created, so the frame vanished as soon as the
        # camera moved (Maya 2023, 2026-10-17).
        return False

    def boundingBox(self):
        return _bounds(om.MDagPath.getAPathTo(self.thisMObject()))


class GuideData(om.MUserData):
    def __init__(self):
        super().__init__(False)       # keep the data between draws
        self.corners = []
        self.text = ""
        self.camera = None
        self.line_width = 2.0


def _plug(fn, name):
    return fn.findPlug(name, False)


def _transform_name(path):
    """Full name of the camera's transform, whether `path` names the transform or the shape."""
    p = om.MDagPath(path)
    if not p.node().hasFn(om.MFn.kTransform):
        p.pop()
    return p.fullPathName()


_warned = set()


def _warn_once(text):
    if text not in _warned:
        _warned.add(text)
        om.MGlobal.displayWarning(text)


# Diagnosis (tools/maya_guide_diagnose.py): with SYNCBRIDGE_GUIDE_DEBUG set, print the first
# few calls of each drawing step to the Script Editor.
_debug_counts = {}


def _debug(step, text):
    if not os.environ.get("SYNCBRIDGE_GUIDE_DEBUG"):
        return
    count = _debug_counts.get(step, 0)
    if count < 3:
        _debug_counts[step] = count + 1
        print("[SyncBridge guide debug] %s: %s" % (step, text))


def _camera_values(cam_fn):
    dep = om.MFnDependencyNode(cam_fn.object())
    return {
        "orthographic": cam_fn.isOrtho(),
        "orthographic_width": _plug(dep, "orthographicWidth").asDouble(),
        "focal_length": _plug(dep, "focalLength").asDouble(),
        "h_aperture": _plug(dep, "horizontalFilmAperture").asDouble(),
        "v_aperture": _plug(dep, "verticalFilmAperture").asDouble(),
        "h_offset": _plug(dep, "horizontalFilmOffset").asDouble(),
        "v_offset": _plug(dep, "verticalFilmOffset").asDouble(),
        "film_fit": _plug(dep, "filmFit").asInt(),
        "near": _plug(dep, "nearClipPlane").asDouble(),
        "far": _plug(dep, "farClipPlane").asDouble(),
    }


def _render_values():
    sel = om.MSelectionList()
    sel.add("defaultResolution")
    dep = om.MFnDependencyNode(sel.getDependNode(0))
    return {"width": _plug(dep, "width").asInt(), "height": _plug(dep, "height").asInt(),
            "device_aspect": _plug(dep, "deviceAspectRatio").asFloat(),
            "pixel_aspect": _plug(dep, "pixelAspect").asFloat()}


def _camera_path(node):
    """The camera shape connected to node.cameraMatrix (cameraShape.worldMatrix[0])."""
    source = _plug(node, "cameraMatrix").source()
    if source.isNull:
        raise ValueError("no camera is connected to cameraMatrix")
    path = om.MDagPath.getAPathTo(source.node())
    if not path.node().hasFn(om.MFn.kCamera):
        path.extendToShape()
    return path


def _compute(guide_path):
    """Frame of the guide in the guide's local space.

    Returns (corners [(x, y, z)], label, camera transform name, details for debugging)."""
    node = om.MFnDependencyNode(guide_path.node())
    comp = comp_guide.parse_comp({"name": _plug(node, "compName").asString(),
                                  "width": _plug(node, "compWidth").asInt(),
                                  "height": _plug(node, "compHeight").asInt()})
    cam_path = _camera_path(node)
    cam = _camera_values(om.MFnCamera(cam_path))
    render = _render_values()
    distance = comp_guide.draw_distance(cam["near"], cam["far"])
    rect = comp_guide.guide_rect(cam, render, comp, distance)
    # camera space -> world -> the guide's local space (its transform is normally the identity)
    to_local = cam_path.inclusiveMatrix() * guide_path.inclusiveMatrixInverse()
    corners = []
    for x, y, z in rect["corners"]:
        p = om.MPoint(x, y, z) * to_local
        corners.append((p.x, p.y, p.z))
    camera = _transform_name(cam_path)
    details = "camera=%s ortho=%s orthoWidth=%g near=%g far=%g distance=%g render=%sx%s" % (
        camera, cam["orthographic"], cam["orthographic_width"], cam["near"], cam["far"], distance,
        render["width"], render["height"])
    return corners, comp_guide.label(comp, render), camera, details


def _bounds(guide_path):
    box = om.MBoundingBox()
    try:
        corners = _compute(guide_path)[0]
        for x, y, z in corners:
            box.expand(om.MPoint(x, y, z))
        pad = max(box.width, box.height, box.depth) * 0.05 + 1e-4       # never flat
        box.expand(om.MPoint(box.min.x - pad, box.min.y - pad, box.min.z - pad))
        box.expand(om.MPoint(box.max.x + pad, box.max.y + pad, box.max.z + pad))
    except Exception as exc:
        _warn_once("SyncBridge guide: cannot compute the bounding box: %s" % exc)
        box.expand(om.MPoint(-1.0, -1.0, -1.0))
        box.expand(om.MPoint(1.0, 1.0, 1.0))
    _debug("boundingBox", "min=%s max=%s" % (
        [round(v, 4) for v in (box.min.x, box.min.y, box.min.z)],
        [round(v, 4) for v in (box.max.x, box.max.y, box.max.z)]))
    return box


class CompGuideDrawOverride(omr.MPxDrawOverride):
    @staticmethod
    def creator(obj):
        return CompGuideDrawOverride(obj)

    @staticmethod
    def draw(context, data):
        """Unused (everything is drawn in addUIDrawables); Autodesk's footPrintNode example
        passes a draw callback too."""
        return

    def __init__(self, obj):
        # always dirty: follow camera / resolution edits
        super().__init__(obj, CompGuideDrawOverride.draw, True)
        _debug("override created", om.MFnDependencyNode(obj).name())

    def supportedDrawAPIs(self):
        return omr.MRenderer.kAllDevices

    def hasUIDrawables(self):
        return True

    def isBounded(self, obj_path, camera_path):
        _debug("isBounded", obj_path.fullPathName())
        return False          # never culled (see CompGuideNode.isBounded)

    def boundingBox(self, obj_path, camera_path):
        return _bounds(obj_path)

    def prepareForDraw(self, obj_path, camera_path, frame_context, old_data):
        _debug("prepareForDraw called", obj_path.fullPathName())
        try:
            data = old_data if isinstance(old_data, GuideData) else GuideData()
            data.corners, data.text, data.camera = [], "", None
            node = om.MFnDependencyNode(obj_path.node())
            data.line_width = _plug(node, "lineWidth").asFloat()
            corners, data.text, data.camera, details = _compute(obj_path)
            data.corners = [om.MPoint(x, y, z) for (x, y, z) in corners]
            _debug("prepareForDraw", "%s corners=%s" % (details, [tuple(round(v, 4) for v in c) for c in corners]))
            return data
        except Exception as exc:              # never break the viewport, but say why nothing is drawn
            _warn_once("SyncBridge guide: cannot compute the frame: %s" % exc)
            return GuideData()

    def addUIDrawables(self, obj_path, draw_manager, frame_context, data):
        if not isinstance(data, GuideData) or not data.corners:
            _debug("addUIDrawables", "nothing to draw (data type %s, corners %s)"
                   % (type(data).__name__, bool(getattr(data, "corners", None))))
            return
        try:
            view_camera = _transform_name(frame_context.getCurrentCameraPath())
            if view_camera != data.camera:
                _debug("addUIDrawables", "skipped: view camera %s, guide camera %s" % (view_camera, data.camera))
                return                         # another camera's view
        except Exception as exc:
            _warn_once("SyncBridge guide: cannot tell the view's camera (%s); drawing anyway" % exc)
        try:
            draw_manager.beginDrawable()
            draw_manager.setColor(COLOR)
            draw_manager.setLineWidth(data.line_width)
            pts = data.corners
            for i in range(4):
                draw_manager.line(pts[i], pts[(i + 1) % 4])
            draw_manager.text(pts[3], data.text, omr.MUIDrawManager.kLeft)
            draw_manager.endDrawable()
            _debug("addUIDrawables", "drew the frame for %s" % data.camera)
        except Exception as exc:
            _warn_once("SyncBridge guide: drawing failed: %s" % exc)


# ---- key markers overlay (D-18) -------------------------------------------------------------
# A second plug-in shape: shows "AE キー 3/8  素材 36f" in the top-left corner of all views while the
# current frame is on an AE key. Drawn in screen space (2D), so it needs no camera. The markers
# are read from the scene's syncBridgeKeyMarkers network node on every draw (no connection:
# a new transfer replaces that node, and an undo brings the old one back).
# Not yet run in the GUI (H-MY-24): MUIDrawManager.text2d / circle2d,
# MFrameContext.getViewportDimensions. MAnimControl (in OpenMayaAnim) works in mayapy 2023 / 2024.

MARKER_NODE_NAME = "syncBridgeKeyMarker"
MARKER_NODE_ID = om.MTypeId(0x0007F5B1)
MARKER_CLASSIFICATION = "drawdb/geometry/syncBridgeKeyMarker"
MARKER_REGISTRANT = "SyncBridgeKeyMarkerPlugin"


MARKER_DATA_NODE = "syncBridgeKeyMarkers"      # syncbridge_maya.key_markers.DATA_NODE
_parsed = {"text": None, "markers": []}


class KeyMarkerNode(om.MPxSurfaceShape):
    @staticmethod
    def creator():
        return KeyMarkerNode()

    @staticmethod
    def initialize():
        pass

    def excludeAsPluginShape(self):
        return True           # own Show menu item, not "Plugin Shapes" (see DISPLAY_FILTERS)

    def isBounded(self):
        return False          # screen-space overlay, never culled


def _stored_markers():
    """Markers of the scene's network node (parsed again only when its text changes)."""
    sel = om.MSelectionList()
    try:
        sel.add(MARKER_DATA_NODE)
    except RuntimeError:          # no markers in this scene
        return []
    text = _plug(om.MFnDependencyNode(sel.getDependNode(0)), "markers").asString()
    if text != _parsed["text"]:
        _parsed["text"] = text
        _parsed["markers"] = (json.loads(text) or {}).get("markers") or [] if text else []
    return _parsed["markers"]


class KeyMarkerData(om.MUserData):
    def __init__(self):
        super().__init__(False)
        self.text = ""


def _current_frame():
    return oma.MAnimControl.currentTime().asUnits(om.MTime.uiUnit())     # OpenMayaAnim, not OpenMaya


# All views, not only the active one: Maya's default "Playback > Update View: Active"
# (playbackOptions -view "active", checked in mayapy 2023 / 2024) redraws only the active view
# while the time changes, so the marker showed there only. When the marker to show changes
# (a key reached or left), every view is asked to redraw. The user's setting is not changed.
_marker_state = {"label": None}


def _refresh_all_views():
    omui.M3dView.scheduleRefreshAllViews()


def _time_changed(*_args):
    try:
        label = None
        markers = _stored_markers()
        if markers:
            marker = core_markers.marker_at(markers, _current_frame())
            label = marker["label"] if marker is not None else None
        if label != _marker_state["label"]:
            _marker_state["label"] = label
            _refresh_all_views()
    except Exception as exc:
        _warn_once("SyncBridge key markers: %s" % exc)


class KeyMarkerDrawOverride(omr.MPxDrawOverride):
    @staticmethod
    def creator(obj):
        return KeyMarkerDrawOverride(obj)

    @staticmethod
    def draw(context, data):
        return

    def __init__(self, obj):
        super().__init__(obj, KeyMarkerDrawOverride.draw, True)     # always dirty: follows the time
        _debug("marker override created", om.MFnDependencyNode(obj).name())

    def supportedDrawAPIs(self):
        return omr.MRenderer.kAllDevices

    def hasUIDrawables(self):
        return True

    def isBounded(self, obj_path, camera_path):
        return False

    def prepareForDraw(self, obj_path, camera_path, frame_context, old_data):
        data = old_data if isinstance(old_data, KeyMarkerData) else KeyMarkerData()
        data.text = ""
        try:
            marker = core_markers.marker_at(_stored_markers(), _current_frame())
            if marker is not None:
                data.text = marker["label"]
            _debug("marker prepareForDraw", "frame=%g text=%r" % (_current_frame(), data.text))
        except Exception as exc:
            _warn_once("SyncBridge key markers: %s" % exc)
        return data

    def addUIDrawables(self, obj_path, draw_manager, frame_context, data):
        if not isinstance(data, KeyMarkerData) or not data.text:
            return
        try:
            x, y, width, height = frame_context.getViewportDimensions()
            top = y + height - 36
            draw_manager.beginDrawable()
            draw_manager.setColor(COLOR)
            draw_manager.circle2d(om.MPoint(x + 22, top + 6), 7.0, True)
            draw_manager.text2d(om.MPoint(x + 36, top), data.text, omr.MUIDrawManager.kLeft)
            draw_manager.endDrawable()
            _debug("marker addUIDrawables", "drew %r" % data.text)
        except Exception as exc:
            _warn_once("SyncBridge key markers: drawing failed: %s" % exc)


# Show menu (D-20): users often hide locators, so the guide and the marker overlay are plug-in
# shapes, not locators, leave the "Plugin Shapes" filter (excludeAsPluginShape) and get their own
# items in each view's Show menu (pluginDisplayFilter). H-MY-27, Maya 2025 GUI (user's PC,
# 2026-10-20, test plug-in): a locator with excludeAsLocator still hid with "Locators"; a
# surface shape with excludeAsPluginShape stayed and hid with its own item only.


class GuideShapeUI(omui.MPxSurfaceShapeUI):
    """Required by registerShape; all drawing is in the Viewport 2.0 draw overrides."""

    @staticmethod
    def creator():
        return GuideShapeUI()


DISPLAY_FILTERS = (
    ("syncBridgeCompGuideFilter", u"SyncBridge 解像度の枠", DRAW_CLASSIFICATION),
    ("syncBridgeKeyMarkerFilter", u"SyncBridge キーのマーカー", MARKER_CLASSIFICATION),
)


def _register_display_filters():
    import maya.cmds as cmds
    for name, label, classification in DISPLAY_FILTERS:
        if not cmds.pluginDisplayFilter(name, query=True, exists=True):
            cmds.pluginDisplayFilter(name, register=True, label=label, classification=classification)


def _deregister_display_filters():
    import maya.cmds as cmds
    for name, _label, _classification in DISPLAY_FILTERS:
        if cmds.pluginDisplayFilter(name, query=True, exists=True):
            cmds.pluginDisplayFilter(name, deregister=True)


# Saving: take the guides and the marker overlay out just before and put them back just after,
# so the file has no `requires "syncbridge_guide.py"` (setDoNotWrite alone keeps the nodes out
# but not the requires line, Maya 2024; H-MY-22). The work is in syncbridge_maya.
_callbacks = []
_stash = {}


def _before_save(*_args):
    _stash.clear()
    try:
        from syncbridge_maya import comp_guide as maya_guide, key_markers
        _stash["guides"] = maya_guide.take_out_for_save()
        _stash["markers"] = key_markers.take_out_for_save()
    except Exception as exc:          # never block the user's save
        om.MGlobal.displayWarning("SyncBridge guide: %s" % exc)


def _after_save(*_args):
    try:
        from syncbridge_maya import comp_guide as maya_guide, key_markers
        maya_guide.put_back_after_save(list(_stash.get("guides") or []))
        key_markers.put_back_after_save(bool(_stash.get("markers")))
    except Exception as exc:
        om.MGlobal.displayWarning("SyncBridge guide: %s" % exc)
    finally:
        _stash.clear()


def _after_open(*_args):
    """A scene with stored key markers shows them again while this plug-in is loaded."""
    try:
        from syncbridge_maya import key_markers
        key_markers.restore_overlay()
    except Exception as exc:
        om.MGlobal.displayWarning("SyncBridge key markers: %s" % exc)


def _report(step):
    """Maya shows only "# Error: (syncbridge_guide)" when these fail; print the reason first."""
    import traceback
    print("[SyncBridge guide] %s failed:" % step)
    traceback.print_exc()


def initializePlugin(obj):
    try:
        plugin = om.MFnPlugin(obj, "SyncBridge", "1.1", "Any")
        _import_core(plugin.loadPath())
        plugin.registerShape(NODE_NAME, NODE_ID, CompGuideNode.creator, CompGuideNode.initialize,
                             GuideShapeUI.creator, DRAW_CLASSIFICATION)
        omr.MDrawRegistry.registerDrawOverrideCreator(DRAW_CLASSIFICATION, DRAW_REGISTRANT,
                                                      CompGuideDrawOverride.creator)
        plugin.registerShape(MARKER_NODE_NAME, MARKER_NODE_ID, KeyMarkerNode.creator, KeyMarkerNode.initialize,
                             GuideShapeUI.creator, MARKER_CLASSIFICATION)
        omr.MDrawRegistry.registerDrawOverrideCreator(MARKER_CLASSIFICATION, MARKER_REGISTRANT,
                                                      KeyMarkerDrawOverride.creator)
        _register_display_filters()
        _callbacks.append(om.MSceneMessage.addCallback(om.MSceneMessage.kBeforeSave, _before_save))
        _callbacks.append(om.MSceneMessage.addCallback(om.MSceneMessage.kAfterSave, _after_save))
        _callbacks.append(om.MSceneMessage.addCallback(om.MSceneMessage.kAfterOpen, _after_open))
        _callbacks.append(om.MEventMessage.addEventCallback("timeChanged", _time_changed))
    except Exception:
        _report("initializePlugin")
        raise


def uninitializePlugin(obj):
    try:
        plugin = om.MFnPlugin(obj)
        for callback_id in _callbacks:
            om.MMessage.removeCallback(callback_id)
        del _callbacks[:]
        _deregister_display_filters()
        omr.MDrawRegistry.deregisterDrawOverrideCreator(MARKER_CLASSIFICATION, MARKER_REGISTRANT)
        plugin.deregisterNode(MARKER_NODE_ID)
        omr.MDrawRegistry.deregisterDrawOverrideCreator(DRAW_CLASSIFICATION, DRAW_REGISTRANT)
        plugin.deregisterNode(NODE_ID)
    except Exception:
        _report("uninitializePlugin")
        raise
