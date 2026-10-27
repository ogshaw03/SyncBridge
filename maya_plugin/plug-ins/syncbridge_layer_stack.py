"""SyncBridge layer stack view (D-32, prototype): a Viewport 2.0 render override that draws the
SyncBridge Maya layers on top of each other in one view, like AE layers.

Each Maya layer is one scene pass with its own camera (its dedicated camera, D-29) and only its own
objects. The first pass clears the view; the others clear only the depth, so a layer is drawn over the
layers below it whatever their depth (AE's stacking). Then the HUD and the present.

    hypotheses (GUI only, mayapy has no viewport): H-MY-33
      MSceneRender.cameraOverride() draws the pass through that camera (film offset / pan / zoom too),
      objectSetOverride() draws only those objects (with the children of a transform),
      clearOperation() with kClearDepth keeps the color of the passes before.

The HUD draws the AE comp frame (the size of the D-16 comp guide of the view's camera) with
syncbridge.core.view_frame: from the film back, Film Fit and overscan only, so a film translate / offset /
pan of the camera does not move it (D-34). Maya's resolution gate is not drawn here and would turn the
overscan to 1.3 (D-27), and the guide node's own drawing is never called inside the stack (H-MY-36).

While the comp frame is shown, the stack can be zoomed out by a margin to show the area around the frame
(D-35): each layer is drawn with a projection made from its camera model (core.stack_view, the model the
renders confirmed) shrunk around the view's center, and the frame shrinks the same. No camera changes.

The layers come from syncbridge_maya.layer_stack.publish(), through __main__ (the script modules may
be reloaded by the SB Dev button, the plug-in is not):
    __main__._syncbridge_layer_stack = {"version": n, "layers": [(name, camera dag path, [dag paths])],
                                        "overlay": (camera dag path, {width, height, name}) or None,
                                        "margin": 1.0 = none, 1.2 = 20 %,
                                        "shade": 0.0 - 1.0, the opacity outside the frame,
                                        "editing": (dedicated camera, viewer camera) dag paths or None}

The viewer's 2D pan / zoom (D-44): the editing layer is drawn through the viewer camera (its dedicated
camera with free 2D pan / zoom that Maya's 2D Pan/Zoom tool changes, syncbridge_maya.viewer_camera); the
other layers and the comp frame go through the same change of the picture (core.stack_view.view_affine),
which replaces the margin while a layer is edited.
"""
from __future__ import annotations

import os
import sys

import maya.api.OpenMaya as om
import maya.api.OpenMayaRender as omr
import maya.api.OpenMayaUI as omui

OVERRIDE_NAME = "SyncBridgeLayerStack"
REVISION = 11                                      # shown in uiName: is the plug-in really reloaded?
UI_NAME = "SyncBridge Layer Stack r%d" % REVISION
STATE_KEY = "_syncbridge_layer_stack"
FRAME_COLOR = om.MColor((1.0, 0.55, 0.1, 1.0))       # the comp guide's colour (D-16)
DEFAULT_SHADE = 0.5                                  # outside the frame, like the resolution gate's shade


def shade_color(shade) -> om.MColor:
    """Black at the viewer's "shade" opacity (the user sets it, 2026-10-27)."""
    try:
        alpha = min(1.0, max(0.0, float(shade)))
    except (TypeError, ValueError):
        alpha = DEFAULT_SHADE
    return om.MColor((0.0, 0.0, 0.0, alpha))

core_guide = None      # syncbridge.core.comp_guide, imported in initializePlugin
core_frame = None      # syncbridge.core.view_frame
core_view = None       # syncbridge.core.stack_view (the margin)

# camera attribute -> key of core.pixel_mapping's camera model (the margin's projection, D-35)
MODEL_ATTRS = (("focalLength", "focal_length"), ("horizontalFilmAperture", "hfa"),
               ("verticalFilmAperture", "vfa"), ("horizontalFilmOffset", "hfo"), ("verticalFilmOffset", "vfo"),
               ("filmTranslateH", "ft_h"), ("filmTranslateV", "ft_v"), ("horizontalPan", "hpan"),
               ("verticalPan", "vpan"), ("zoom", "zoom"), ("preScale", "pre_scale"), ("postScale", "post_scale"),
               ("filmRollValue", "film_roll"), ("horizontalRollPivot", "roll_pivot_h"),
               ("verticalRollPivot", "roll_pivot_v"), ("overscan", "overscan"))


def _import_core(plugin_dir):
    """Like syncbridge_guide.py: scripts/ and the repository's src/ next to plug-ins/."""
    global core_guide, core_frame, core_view
    maya_dir = os.path.dirname(os.path.normpath(plugin_dir))
    for path in (os.path.join(maya_dir, "scripts"), os.path.join(os.path.dirname(maya_dir), "src")):
        has_package = any(os.path.isdir(os.path.join(path, p)) for p in ("syncbridge", "syncbridge_maya"))
        if has_package and path not in sys.path:
            sys.path.append(path)
    from syncbridge.core import comp_guide as module
    from syncbridge.core import stack_view as view_module
    from syncbridge.core import view_frame as frame_module
    core_guide = module
    core_frame = frame_module
    core_view = view_module


def model_camera(camera_path) -> dict:
    """The camera for core.pixel_mapping.project (what the margin's projection needs)."""
    fn = om.MFnCamera(camera_path)
    dep = om.MFnDependencyNode(fn.object())
    out = {key: dep.findPlug(attr, False).asDouble() for attr, key in MODEL_ATTRS}
    out.update(film_fit=dep.findPlug("filmFit", False).asInt(),
               film_roll_order=dep.findPlug("filmRollOrder", False).asInt(),
               pan_zoom_enabled=dep.findPlug("panZoomEnabled", False).asBool(),
               orthographic=fn.isOrtho())
    return out


_warned = set()


def _warn_once(text):
    if text not in _warned:
        _warned.add(text)
        om.MGlobal.displayWarning(text)


# Diagnosis: with SYNCBRIDGE_STACK_DEBUG set, print the first few calls of each step.
_debug_counts = {}


def _debug(step, text):
    if not os.environ.get("SYNCBRIDGE_STACK_DEBUG"):
        return
    count = _debug_counts.get(step, 0)
    if count < 3:
        _debug_counts[step] = count + 1
        print("[SyncBridge stack debug] %s: %s" % (step, text))


def maya_useNewAPI():
    pass


def _state() -> dict:
    import __main__
    return getattr(__main__, STATE_KEY, None) or {"version": 0, "layers": []}


def _dag_path(name: str):
    sel = om.MSelectionList()
    try:
        sel.add(name)
        return sel.getDagPath(0)
    except RuntimeError:
        return None


class LayerPass(omr.MSceneRender):
    """One SyncBridge Maya layer: its camera, its objects. Made once and reused (see LayerStackOverride)."""

    def __init__(self, name):
        super().__init__(name)
        self._camera = omr.MCameraOverride()
        self._objects = om.MSelectionList()
        self._first = True
        self.camera_path = None

    def set_layer(self, camera, objects, first):
        """Refill in place: the objects Maya was given stay alive."""
        self._camera.mCameraPath = camera
        self.camera_path = camera
        self._objects.clear()
        self._objects.merge(objects)
        self._first = first

    def set_projection(self, rows):
        """The margin's projection (16 numbers, D-35), or None for the camera's own."""
        if rows is None:
            self._camera.mUseProjectionMatrix = False
        else:
            self._camera.mProjectionMatrix = om.MMatrix(rows)
            self._camera.mUseProjectionMatrix = True

    def cameraOverride(self):
        return self._camera

    def objectSetOverride(self):
        return self._objects

    def clearOperation(self):
        op = self.mClearOperation
        if self._first:
            op.setMask(omr.MClearOperation.kClearAll)
        else:
            op.setMask(omr.MClearOperation.kClearDepth | omr.MClearOperation.kClearStencil)
        return op


def _camera_values(cam_fn):
    """What core.view_frame.frame_rect needs: the film back and Film Fit. The overscan is 1.0, the
    dedicated cameras' (the layers are drawn with them): the original camera's overscan (1.3 while its
    resolution gate is shown) does not reach the stack (D-34)."""
    dep = om.MFnDependencyNode(cam_fn.object())

    def plug(name):
        return dep.findPlug(name, False)
    return {"hfa": plug("horizontalFilmAperture").asDouble(), "vfa": plug("verticalFilmAperture").asDouble(),
            "film_fit": plug("filmFit").asInt(), "overscan": 1.0,
            "lens_squeeze": plug("lensSqueezeRatio").asDouble()}


def _render_values():
    sel = om.MSelectionList()
    sel.add("defaultResolution")
    dep = om.MFnDependencyNode(sel.getDependNode(0))
    return {"width": dep.findPlug("width", False).asInt(), "height": dep.findPlug("height", False).asInt(),
            "device_aspect": dep.findPlug("deviceAspectRatio", False).asFloat(),
            "pixel_aspect": dep.findPlug("pixelAspect", False).asFloat()}


def frame_screen_points(camera_path, comp, viewport, margin=1.0, view=None):
    """The comp frame's 4 corners in view pixels (2D, origin bottom-left) and its label. Only the film
    back, Film Fit, the margin and the render's aspect place it: film translate, offset, pan and roll move
    the picture, not the frame (core.view_frame, D-34). The margin shrinks it like the layers (D-35);
    `view` (the viewer's 2D pan / zoom, an NDC affine map, D-44) moves it like the layers instead."""
    render = _render_values()
    cam = dict(_camera_values(om.MFnCamera(camera_path)), overscan=1.0 if view else float(margin))
    left, bottom, right, top = core_frame.frame_rect(tuple(viewport), cam, render, comp)
    corners = [(left, top), (right, top), (right, bottom), (left, bottom)]
    if view:
        x0, y0, w, h = viewport
        corners = [core_view.map_point(view, ((x - x0) / w * 2.0 - 1.0, (y - y0) / h * 2.0 - 1.0)) for x, y in corners]
        corners = [(x0 + (nx + 1.0) * 0.5 * w, y0 + (ny + 1.0) * 0.5 * h) for nx, ny in corners]
    points = [om.MPoint(x, y) for x, y in corners]
    return points, core_guide.label(comp, render)


def mask_bands(points, viewport):
    """(left, bottom, right, top) of the view outside the frame, in view pixels: the bands below, above,
    left and right of it (empty bands left out). The frame is an upright rectangle on screen."""
    x0, y0, width, height = viewport
    x1, y1 = x0 + width, y0 + height
    left = max(x0, min(min(p.x for p in points), x1))
    right = min(x1, max(max(p.x for p in points), x0))
    bottom = max(y0, min(min(p.y for p in points), y1))
    top = min(y1, max(max(p.y for p in points), y0))
    bands = [(x0, y0, x1, bottom), (x0, top, x1, y1), (x0, bottom, left, top), (right, bottom, x1, top)]
    return [b for b in bands if b[2] - b[0] > 0.5 and b[3] - b[1] > 0.5]


LABEL_GAP = 4.0          # px between the frame and its size label
LABEL_HEIGHT = 16.0      # room a line of HUD text needs


def label_point(points, viewport):
    """Where the size label goes (left-aligned): outside the frame, above its top-left corner (the user,
    2026-10-25); inside that corner when the frame reaches the top of the view (no margin)."""
    x0, y0, width, height = viewport
    left = max(min(p.x for p in points), x0 + LABEL_GAP)
    top = max(p.y for p in points)
    y = top + LABEL_GAP
    if y + LABEL_HEIGHT > y0 + height:
        y = top - LABEL_GAP - LABEL_HEIGHT
    return om.MPoint(left, y)


class FrameHUD(omr.MHUDRender):
    """Maya's HUD plus the AE comp frame of the view's camera."""

    def __init__(self):
        super().__init__()
        self.frame = None                       # (camera MDagPath, comp dict) or None
        self.margin = 1.0
        self.view = None                        # the viewer's 2D pan / zoom (NDC affine, D-44) or None
        self.depth = None                       # columns 2 and 3 of the view's projection (D-35)

    def hasUIDrawables(self):
        _debug("hasUIDrawables", "frame=%s core=%s" % (self.frame is not None, core_guide is not None))
        return True

    def _keep_depth(self, frame_context):
        """The depth and w columns of the projection this device uses, for the margin's projection."""
        try:
            m = frame_context.getMatrix(omr.MFrameContext.kProjectionMtx)
            self.depth = [(m.getElement(i, 2), m.getElement(i, 3)) for i in range(4)]
        except Exception as exc:
            _warn_once("SyncBridge layer stack: cannot read the view's projection: %s" % exc)

    def addUIDrawables(self, draw_manager, frame_context):
        _debug("addUIDrawables called", "frame=%s core=%s" % (
            self.frame and (self.frame[0].fullPathName(), self.frame[1]), core_guide is not None))
        self._keep_depth(frame_context)
        if self.frame is None or core_guide is None or core_frame is None:
            return
        try:
            camera, comp = self.frame
            viewport = frame_context.getViewportDimensions()
            points, text = frame_screen_points(camera, comp, viewport, self.margin, self.view)
            _debug("frame points", "viewport=%s points=%s" % (
                tuple(viewport), [(round(p.x, 1), round(p.y, 1)) for p in points]))
            draw_manager.beginDrawable()
            shade = shade_color(_state().get("shade", DEFAULT_SHADE))
            if shade.a > 0.0:
                draw_manager.setColor(shade)
                for left, bottom, right, top in mask_bands(points, viewport):
                    draw_manager.rect2d(om.MPoint((left + right) / 2.0, (bottom + top) / 2.0),
                                        om.MVector(0.0, 1.0, 0.0), (right - left) / 2.0, (top - bottom) / 2.0, True)
            draw_manager.setColor(FRAME_COLOR)
            draw_manager.setLineWidth(1.5)
            for i in range(4):
                draw_manager.line2d(points[i], points[(i + 1) % 4])
            draw_manager.text2d(label_point(points, viewport), text, omr.MUIDrawManager.kLeft)
            draw_manager.endDrawable()
        except Exception as exc:                # never break the view
            _warn_once("SyncBridge layer stack: cannot draw the comp frame: %s" % exc)


class LayerStackOverride(omr.MRenderOverride):
    """The operations are made once and kept for the life of the override: rebuilding them when the
    layers changed let Python free a pass that Maya still used, and Maya crashed when the eye of a layer
    was toggled quickly (the user, 2026-10-25). A change only refills the passes."""

    def __init__(self, name):
        super().__init__(name)
        self._pool = []                                    # LayerPass, never freed
        self._scene = omr.MSceneRender("SyncBridgeLayerStack_scene")
        self._hud = FrameHUD()
        self._present = omr.MPresentTarget("SyncBridgeLayerStack_present")
        self._ops = [self._scene, self._hud, self._present]
        self._index = 0
        self._version = None
        self._editing = None

    def _pass(self, i):
        while len(self._pool) <= i:
            self._pool.append(LayerPass("SyncBridgeLayer_%d" % len(self._pool)))
        return self._pool[i]

    def uiName(self):
        return UI_NAME

    def supportedDrawAPIs(self):
        return omr.MRenderer.kAllDevices

    def _build(self):
        state = _state()
        if state["version"] == self._version and self._ops:
            return
        self._version = state["version"]
        editing = state.get("editing")
        self._editing = None                    # (dedicated camera, viewer camera) MDagPaths, D-44
        if editing:
            dedicated, viewer = _dag_path(editing[0]), _dag_path(editing[1])
            if dedicated is not None and viewer is not None:
                self._editing = (dedicated, viewer)
        ops = []
        for name, camera_name, object_names in state["layers"]:
            camera = _dag_path(camera_name)
            if camera is not None and self._editing is not None and camera == self._editing[0]:
                camera = self._editing[1]       # the editing layer: through the viewer camera, as Maya picks
            objects = om.MSelectionList()
            for obj in object_names:
                try:
                    objects.add(obj)
                except RuntimeError:          # gone from the scene: skipped
                    pass
            if camera is None or objects.isEmpty():
                continue
            layer_pass = self._pass(len(ops))
            layer_pass.set_layer(camera, objects, first=not ops)
            ops.append(layer_pass)
        if not ops:                            # nothing to stack: draw the view as usual
            ops.append(self._scene)
        overlay = state.get("overlay")
        camera = _dag_path(overlay[0]) if overlay else None
        self._hud.frame = (camera, dict(overlay[1])) if camera is not None else None
        self._ops = ops + [self._hud, self._present]
        _debug("build", "version=%s layers=%d overlay=%s ops=%s" % (
            self._version, len(state["layers"]), overlay, [type(op).__name__ for op in self._ops]))

    def setup(self, destination):
        try:
            self._build()
        except Exception as exc:  # never raise into the draw: keep the last good passes
            om.MGlobal.displayWarning("SyncBridge layer stack: %s" % exc)
        try:
            if self._editing is not None and self._hud.depth is not None and core_view is not None:
                self._view(destination)
            else:
                self._hud.view = None
                self._margin(destination)
        except Exception as exc:  # the stack without the margin rather than no stack
            _warn_once("SyncBridge layer stack: the margin / 2D pan-zoom is off (%s)" % exc)
            for layer_pass in self._pool:
                layer_pass.set_projection(None)
            self._hud.margin = 1.0
            self._hud.view = None

    def _view(self, destination):
        """The viewer's 2D pan / zoom (D-44): the editing layer through the viewer camera (Maya's own
        projection), the others through the same change of the picture."""
        dedicated, viewer = self._editing
        view = omui.M3dView.getM3dViewFromModelPanel(destination)
        width, height = view.portWidth(), view.portHeight()
        affine = core_view.view_affine(model_camera(dedicated), model_camera(viewer), width, height)
        for layer_pass in [op for op in self._ops if isinstance(op, LayerPass)]:
            if layer_pass.camera_path == viewer:
                layer_pass.set_projection(None)
                continue
            cam = model_camera(layer_pass.camera_path)
            if cam["orthographic"]:
                _warn_once("SyncBridge layer stack: the 2D pan / zoom does not reach orthographic cameras")
                layer_pass.set_projection(None)
                continue
            fn = om.MFnCamera(layer_pass.camera_path)
            rows = core_view.compose(affine, core_view.ndc_affine(cam, width, height))
            layer_pass.set_projection(core_view.projection_rows(rows, self._hud.depth, fn.nearClippingPlane,
                                                                fn.farClippingPlane))
        self._hud.margin = 1.0
        self._hud.view = affine
        _debug("view", "affine %s view %dx%d" % (tuple(round(v, 4) for v in affine), width, height))

    def _margin(self, destination):
        """Zoom the stack out by the margin while the comp frame is shown (D-35): every layer gets the
        projection of its camera model shrunk around the view's center, the frame shrinks the same."""
        state = _state()
        margin = float(state.get("margin") or 1.0) if self._hud.frame is not None else 1.0
        layers = [op for op in self._ops if isinstance(op, LayerPass)]
        if margin <= 1.0 + 1e-9 or core_view is None:
            for layer_pass in layers:
                layer_pass.set_projection(None)
            self._hud.margin = 1.0
            return
        view = omui.M3dView.getM3dViewFromModelPanel(destination)
        width, height = view.portWidth(), view.portHeight()
        for layer_pass in layers:
            cam = model_camera(layer_pass.camera_path)
            if cam["orthographic"]:
                _warn_once("SyncBridge layer stack: the margin does not shrink orthographic cameras")
                layer_pass.set_projection(None)
                continue
            fn = om.MFnCamera(layer_pass.camera_path)
            affine = core_view.ndc_affine(cam, width, height, margin)
            layer_pass.set_projection(core_view.projection_rows(affine, self._hud.depth, fn.nearClippingPlane,
                                                                fn.farClippingPlane))
        self._hud.margin = margin
        _debug("margin", "%g view %dx%d" % (margin, width, height))

    def cleanup(self):
        self._index = 0

    def startOperationIterator(self):
        self._index = 0
        return True

    def renderOperation(self):
        return self._ops[self._index] if self._index < len(self._ops) else None

    def nextRenderOperation(self):
        self._index += 1
        return self._index < len(self._ops)


_override = None


def initializePlugin(obj):
    global _override
    plugin = om.MFnPlugin(obj, "SyncBridge", "0.1", "Any")
    try:
        _import_core(plugin.loadPath())
    except Exception as exc:                    # the stack still works, without the comp frame
        _warn_once("SyncBridge layer stack: the comp frame is off (%s)" % exc)
    _override = LayerStackOverride(OVERRIDE_NAME)
    omr.MRenderer.registerOverride(_override)


def uninitializePlugin(obj):
    global _override
    if _override is not None:
        omr.MRenderer.deregisterOverride(_override)
        _override = None
