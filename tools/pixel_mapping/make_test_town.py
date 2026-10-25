"""Test BG model for Pixel Mapping's relative mode (D-25): a small town of buildings at many depths, a
shot camera, and the large BG image for AE rendered from the same place with a wider angle.

In Maya (Script Editor, Python tab):
    exec(open(r"<SyncBridge>/tools/pixel_mapping/make_test_town.py", encoding="utf-8").read())
    make_test_town(out_dir=r"C:/temp/sb_town")              # new scene recommended

Or mayapy:  mayapy make_test_town.py <out_dir>

Makes:
  * SB_TOWN: ground + buildings (boxes) from 10 to 300 units away, colored checker textures
  * SHOT_CAM: focal 35, film 1.417 x 0.945 (3:2), Fit Fill, render 1920 x 1080. With camera_work=True it
    also gets keys (a truck on translateX and a film offset drift over frames 1-48), like a real cut.
  * <out_dir>/town_bg_5760x3240.png: the view of SHOT_CAM at frame 1 with a 3x wider film (same lens center,
    same pixel size), rendered by Hardware 2.0. In AE, a 1920 x 1080 comp with this image as a 2D layer at
    Position (960, 540) (anchor at its center) shows exactly what SHOT_CAM shows at frame 1 (the reference).
    Sliding the layer in AE and sending it moves SHOT_CAM's 2D Pan by the same pixels.
Hardware 2.0's texture size limit is turned off for the render and restored afterwards.
"""
import os

import maya.cmds as cmds

W, H = 1920, 1080
FACTOR = 3                    # BG image = 3 x the shot: 5760 x 3240
HFA, VFA, FOCAL = 1.417, 0.945, 35.0

BUILDINGS = [
    # x, z (distance from the camera ~ 40 - z), width, depth, height, color
    (-9, 22, 4, 4, 8, (0.85, 0.35, 0.30)), (-3, 18, 3, 3, 12, (0.30, 0.65, 0.85)),
    (4, 20, 5, 4, 6, (0.95, 0.80, 0.30)), (11, 14, 4, 5, 15, (0.45, 0.80, 0.45)),
    (-16, 0, 6, 6, 18, (0.70, 0.45, 0.85)), (-6, -5, 5, 5, 25, (0.90, 0.55, 0.20)),
    (6, -2, 6, 5, 14, (0.35, 0.45, 0.90)), (18, -8, 7, 6, 22, (0.85, 0.30, 0.55)),
    (-30, -40, 10, 10, 35, (0.55, 0.75, 0.70)), (-10, -60, 12, 10, 50, (0.80, 0.70, 0.55)),
    (15, -50, 10, 12, 40, (0.50, 0.55, 0.80)), (35, -70, 14, 12, 60, (0.75, 0.50, 0.40)),
    (-60, -150, 25, 20, 90, (0.60, 0.60, 0.75)), (0, -200, 30, 25, 120, (0.70, 0.75, 0.60)),
    (70, -260, 30, 25, 100, (0.80, 0.65, 0.70)),
]


def _shader(name, color):
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    checker = cmds.shadingNode("checker", asTexture=True, name=name + "_checker")
    place = cmds.shadingNode("place2dTexture", asUtility=True, name=name + "_place")
    cmds.connectAttr(place + ".outUV", checker + ".uv")
    cmds.connectAttr(place + ".outUvFilterSize", checker + ".uvFilterSize")
    cmds.setAttr(place + ".repeatU", 6)
    cmds.setAttr(place + ".repeatV", 6)
    cmds.setAttr(checker + ".color1", *color, type="double3")
    cmds.setAttr(checker + ".color2", color[0] * 0.35, color[1] * 0.35, color[2] * 0.35, type="double3")
    cmds.connectAttr(checker + ".outColor", shader + ".color")
    cmds.setAttr(shader + ".incandescence", 0.35, 0.35, 0.35, type="double3")   # readable without lights
    sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", sg + ".surfaceShader")
    return sg


def build_town():
    grp = cmds.group(empty=True, name="SB_TOWN")
    ground = cmds.polyPlane(name="ground", w=800, h=800, sx=1, sy=1)[0]
    cmds.setAttr(ground + ".translate", 0, 0, -300)
    cmds.sets(ground, edit=True, forceElement=_shader("sb_ground", (0.55, 0.55, 0.50)))
    cmds.parent(ground, grp)
    for i, (x, z, w, d, h, color) in enumerate(BUILDINGS):
        box = cmds.polyCube(name="building%02d" % i, w=w, d=d, h=h)[0]
        cmds.setAttr(box + ".translate", x, h / 2.0, z)
        cmds.sets(box, edit=True, forceElement=_shader("sb_bld%02d" % i, color))
        cmds.parent(box, grp)
    return grp


def make_camera(name, aperture_scale=1.0):
    cam = cmds.camera(name=name)[0]
    shape = cmds.listRelatives(cam, shapes=True, fullPath=True)[0]
    cmds.setAttr(shape + ".horizontalFilmAperture", HFA * aperture_scale)
    cmds.setAttr(shape + ".verticalFilmAperture", VFA * aperture_scale)
    cmds.setAttr(shape + ".filmFit", 0)                    # Fill (3:2 film, 16:9 render: fits horizontally)
    cmds.setAttr(shape + ".focalLength", FOCAL)
    cmds.setAttr(shape + ".farClipPlane", 5000)
    cmds.setAttr(cam + ".translate", 0, 8, 40)
    cmds.setAttr(cam + ".rotate", -4, 0, 0)
    return cam, shape


def render_bg(shape, out_dir):
    """The large BG image from `shape` (already widened) with Hardware 2.0."""
    path = os.path.join(out_dir, "town_bg_%dx%d" % (W * FACTOR, H * FACTOR)).replace("\\", "/")
    old = cmds.getAttr("hardwareRenderingGlobals.enableTextureMaxRes")
    cmds.setAttr("hardwareRenderingGlobals.enableTextureMaxRes", False)
    old_prefix = cmds.getAttr("defaultRenderGlobals.imageFilePrefix")
    old_format = cmds.getAttr("defaultRenderGlobals.imageFormat")
    old_rules = cmds.workspace(fileRuleEntry="images")
    try:
        cmds.workspace(fileRule=["images", out_dir])
        cmds.setAttr("defaultRenderGlobals.imageFormat", 32)                 # PNG
        cmds.setAttr("defaultRenderGlobals.imageFilePrefix", os.path.basename(path), type="string")
        result = cmds.ogsRender(camera=shape, width=W * FACTOR, height=H * FACTOR)
    finally:
        cmds.setAttr("hardwareRenderingGlobals.enableTextureMaxRes", old)
        cmds.setAttr("defaultRenderGlobals.imageFilePrefix", old_prefix or "", type="string")
        cmds.setAttr("defaultRenderGlobals.imageFormat", old_format)
        cmds.workspace(fileRule=["images", old_rules])
    return result


def make_test_town(out_dir, camera_work=False):
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    cmds.setAttr("defaultResolution.width", W)
    cmds.setAttr("defaultResolution.height", H)
    cmds.setAttr("defaultResolution.deviceAspectRatio", float(W) / H)
    cmds.setAttr("defaultResolution.pixelAspect", 1.0)
    build_town()
    cmds.currentTime(1)
    shot, shot_shape = make_camera("SHOT_CAM")
    # the BG camera: same place, film FACTOR times wider -> same pixel size, FACTOR times the view
    bg_cam, bg_shape = make_camera("BG_RENDER_CAM", aperture_scale=FACTOR)
    image = render_bg(bg_shape, out_dir)
    cmds.delete(bg_cam)
    if camera_work:
        cmds.setKeyframe(shot, attribute="translateX", time=1, value=0.0)
        cmds.setKeyframe(shot, attribute="translateX", time=48, value=3.0)
        cmds.setKeyframe(shot_shape, attribute="horizontalFilmOffset", time=1, value=0.0)
        cmds.setKeyframe(shot_shape, attribute="horizontalFilmOffset", time=48, value=0.03)
    for s in cmds.ls(type="camera", long=True):
        cmds.setAttr(s + ".renderable", s == shot_shape)
    print("SyncBridge test town: SHOT_CAM, BG image %s" % image)
    print("AE: 1920 x 1080 comp, import the BG image as a 2D layer, Position (960, 540), anchor at its center "
          "(the default). Maya: SyncBridge panel > Pixel Mapping: mode relative, camera SHOT_CAMShape, "
          "2D Pan/Zoom. Frame 1, send once from AE (reference), then slide the layer in AE and send again.")
    return {"camera": shot_shape, "image": image}


def _run_by_mayapy():
    """True only for `mayapy make_test_town.py ...` (exec() in Maya's Script Editor also runs as __main__)."""
    import sys
    return bool(sys.argv) and os.path.basename(sys.argv[0]) == "make_test_town.py"


if __name__ == "__main__" and _run_by_mayapy():
    import sys
    import maya.standalone
    maya.standalone.initialize()
    make_test_town(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.getcwd(), "sb_town"),
                   camera_work="--camera-work" in sys.argv)
