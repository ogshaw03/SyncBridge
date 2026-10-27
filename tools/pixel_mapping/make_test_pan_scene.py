"""Test scene for a horizontal PAN cut made the anime way (GUI Maya, Script Editor, Python tab): Maya renders
the layers with a still camera, AE slides them to make the PAN, SyncBridge brings the slides back.

    exec(open(r"<repository>/tools/pixel_mapping/make_test_pan_scene.py", encoding="utf-8").read())

Laid out like a walk along a hillside path (1 unit = 1 m):
  * PAN_CHAR (red / orange): body, head, a nose box (facing +X) and a backpack, 2.2 m from the camera,
    walking in place (a small bounce, frames 1-96)
  * PAN_BOOK (green): a fence, bushes, trees and grass 6 m from the camera
  * PAN_BG   (blue):  town blocks ~100 m below the path, mountains ~300 m and a sky wall 400 m away
  * checker textures on every layer (press 6 for textures in the view)
  * SHOT_CAM: 1920 x 1080, 16:9 film, 35 mm, still
  * PLATE_BOOK_CAM / PLATE_BG_CAM: the plate cameras of BOOK and BG. Telephoto (200 mm) from far behind
    SHOT_CAM, so a plate 3 times as wide stays nearly flat like a painted BG (a 3 times wider 35 mm film
    would be a 114 degree view, stretched at the ends). At the layer's depth (BOOK 6 m, BG 100 m) they
    show the same size as SHOT_CAM: in AE the plates are used at 100 %.
  * with the SyncBridge panel open: Maya layers CHAR (SHOT_CAM), BOOK (PLATE_BOOK_CAM), BG (PLATE_BG_CAM),
    and new links in source camera mode (D-39)
Then it offers to render the AE material (a folder dialog), also callable as render_material(folder):
  * book_plate_5760x1080.png, bg_plate_5760x1080.png: one frame each, only that layer (alpha)
  * char/char.0001.png ... char.0096.png: 1920 x 1080, only the character (alpha)
In AE: a 1920 x 1080 comp, the three at 100 % in the middle (CHAR on top, BG at the bottom); slide BOOK
fast and BG slowly to the left for the PAN. The scene's playback range and render size are set (it is a
new scene).
"""
import os
import shutil

import maya.cmds as cmds

W, H = 1920, 1080
PLATE_SCALE = 3               # the BOOK / BG plates are 3 times as wide as the shot
START, END = 1, 96
CAM_Z, CAM_Y = 2.2, 1.5       # the character stands on z = 0: waist up in the frame
CHAR_X = -0.1                 # a little left of the frame centre, room ahead of it
BOOK_Z, BG_Z = -3.8, -90.0
PLATE_FOCAL = 200.0
PLATES = [
    # layer, plate camera, depth from SHOT_CAM where the plate shows the same size as SHOT_CAM
    ("BOOK", "PLATE_BOOK_CAM", CAM_Z - BOOK_Z),
    ("BG", "PLATE_BG_CAM", 100.0),
]
LAYERS = [("CHAR", "PAN_CHAR"), ("BOOK", "PAN_BOOK"), ("BG", "PAN_BG")]      # Maya layer order (top first)
COLORS = {
    "char": ((0.95, 0.40, 0.25), (0.60, 0.15, 0.08)), "char_bag": ((0.55, 0.20, 0.15), (0.30, 0.08, 0.05)),
    "book_fence": ((0.20, 0.45, 0.20), (0.08, 0.20, 0.08)), "book_bush": ((0.55, 0.85, 0.30), (0.25, 0.55, 0.15)),
    "book_tree": ((0.35, 0.60, 0.25), (0.15, 0.30, 0.10)),
    "bg_town": ((0.75, 0.82, 0.95), (0.40, 0.50, 0.75)), "bg_mount": ((0.35, 0.50, 0.80), (0.20, 0.32, 0.60)),
    "bg_sky": ((0.55, 0.75, 1.00), (0.40, 0.60, 0.92)),
}


def _shader(name, repeat):
    colors = COLORS[name]
    shader = cmds.shadingNode("lambert", asShader=True, name="pan_" + name)
    checker = cmds.shadingNode("checker", asTexture=True, name="pan_%s_checker" % name)
    place = cmds.shadingNode("place2dTexture", asUtility=True, name="pan_%s_place" % name)
    cmds.connectAttr(place + ".outUV", checker + ".uv")
    cmds.connectAttr(place + ".outUvFilterSize", checker + ".uvFilterSize")
    cmds.setAttr(place + ".repeatU", repeat[0])
    cmds.setAttr(place + ".repeatV", repeat[1])
    cmds.setAttr(checker + ".color1", *colors[0], type="double3")
    cmds.setAttr(checker + ".color2", *colors[1], type="double3")
    cmds.connectAttr(checker + ".outColor", shader + ".color")
    cmds.setAttr(shader + ".incandescence", 0.35, 0.35, 0.35, type="double3")   # readable without lights
    sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name="pan_%sSG" % name)
    cmds.connectAttr(shader + ".outColor", sg + ".surfaceShader")
    return sg


def _put(node, group, sg, translate, rotate=(0, 0, 0)):
    cmds.setAttr(node + ".translate", *translate)
    cmds.setAttr(node + ".rotate", *rotate)
    cmds.sets(node, edit=True, forceElement=sg)
    return cmds.parent(node, group)[0]


def build_char():
    body, bag = _shader("char", (3, 3)), _shader("char_bag", (2, 2))
    grp = cmds.group(empty=True, name="PAN_CHAR")
    _put(cmds.polyCube(name="char_body", w=0.42, h=0.7, d=0.42)[0], grp, body, (0, 1.12, 0))
    _put(cmds.polyCube(name="char_hips", w=0.38, h=0.4, d=0.38)[0], grp, body, (0, 0.6, 0))
    _put(cmds.polyCube(name="char_neck", w=0.12, h=0.12, d=0.12)[0], grp, body, (0.02, 1.52, 0))
    _put(cmds.polySphere(name="char_head", r=0.17, sx=24, sy=16)[0], grp, body, (0.03, 1.72, 0))
    _put(cmds.polyCube(name="char_nose", w=0.07, h=0.05, d=0.05)[0], grp, body, (0.21, 1.71, 0))  # faces +X
    _put(cmds.polyCube(name="char_bag", w=0.2, h=0.5, d=0.36)[0], grp, bag, (-0.31, 1.12, 0))     # on its back
    _put(cmds.polyCube(name="char_arm", w=0.14, h=0.62, d=0.14)[0], grp, body, (0.04, 1.08, 0.29), (0, 0, -8))
    cmds.setAttr(grp + ".translateX", CHAR_X)
    for t in range(START, END + 1, 6):                       # walking in place: a step every 12 frames
        cmds.setKeyframe(grp, attribute="translateY", time=t, value=0.03 if (t - START) % 12 else 0.0)
        cmds.setKeyframe(grp, attribute="rotateZ", time=t, value=(-2.0 if (t - START) % 24 < 12 else 2.0))
    return grp


def build_book():
    fence, bush, tree = _shader("book_fence", (1, 4)), _shader("book_bush", (2, 2)), _shader("book_tree", (2, 6))
    grp = cmds.group(empty=True, name="PAN_BOOK")
    left, right = -14, 14                                    # wider than the 3x plate (+-9.3 m at 6 m)
    for i, x in enumerate(range(left, right + 1, 3)):
        _put(cmds.polyCube(name="book_post%02d" % i, w=0.12, h=1.0, d=0.12)[0], grp, fence, (x, 0.5, BOOK_Z))
        _put(cmds.polySphere(name="book_cap%02d" % i, r=0.09, sx=12, sy=8)[0], grp, fence, (x, 1.05, BOOK_Z))
    for name, y in (("book_rail_top", 0.95), ("book_rail_low", 0.45)):
        _put(cmds.polyCube(name=name, w=right - left, h=0.06, d=0.06)[0], grp, fence, (0, y, BOOK_Z))
    for i, x in enumerate(range(left, right + 1)):
        r = 0.35 + 0.1 * (i % 3)                              # lower than the fence top
        _put(cmds.polySphere(name="book_bush%02d" % i, r=r, sx=12, sy=8)[0], grp, bush,
             (x + 0.4 * (i % 2), r * 0.5, BOOK_Z + 0.5))
    grass = cmds.polyPlane(name="book_ground", w=right - left + 20, h=8, sx=1, sy=1)[0]
    _put(grass, grp, bush, (0, 0, BOOK_Z + 2.5))
    for i, x in enumerate(range(left + 2, right, 7)):
        _put(cmds.polyCylinder(name="book_trunk%02d" % i, r=0.25, h=5.0, sx=12)[0], grp, tree, (x, 2.5, BOOK_Z - 1.5))
        _put(cmds.polySphere(name="book_leaves%02d" % i, r=1.6, sx=16, sy=10)[0], grp, bush, (x + 0.5, 4.6, BOOK_Z - 1.5))
    return grp


def build_bg():
    town, mount, sky = _shader("bg_town", (2, 3)), _shader("bg_mount", (6, 3)), _shader("bg_sky", (24, 6))
    grp = cmds.group(empty=True, name="PAN_BG")
    base = -14.0                                              # the town lies below the hillside path
    for i, x in enumerate(range(-180, 181, 7)):               # wider than the 3x plate (+-155 m at 100 m)
        h = 4 + (i * 5) % 11
        z = BG_Z - 20 * (i % 3)
        _put(cmds.polyCube(name="bg_block%02d" % i, w=5, h=h, d=5)[0], grp, town, (x, base + h / 2.0, z))
    _put(cmds.polyCube(name="bg_tower", w=2, h=22, d=2)[0], grp, town, (30, base + 11, BG_Z - 10))
    # up to under PLATE_BG_CAM (~480 m behind), else the sky shows below the town in its plate
    ground = cmds.polyPlane(name="bg_ground", w=1200, h=1100, sx=1, sy=1)[0]
    _put(ground, grp, mount, (0, base, 150))
    for i, (x, r) in enumerate(((-260, 120), (-130, 100), (-20, 90), (90, 110), (210, 130))):
        m = cmds.polyCone(name="bg_mountain%d" % i, r=r, h=55, sx=24)[0]
        _put(m, grp, mount, (x, 12, -300))
    sky_wall = cmds.polyPlane(name="bg_sky", w=1200, h=300, sx=1, sy=1, axis=(0, 0, 1))[0]
    _put(sky_wall, grp, sky, (0, 80, -400))
    return grp


def _camera(name, focal, z, film_scale=1.0):
    cam = cmds.rename(cmds.camera()[0], name)              # camera(name=...) makes "<name>1"
    shape = cmds.listRelatives(cam, shapes=True, fullPath=True)[0]
    cmds.setAttr(shape + ".horizontalFilmAperture", 1.417 * film_scale)
    cmds.setAttr(shape + ".verticalFilmAperture", 1.417 * H / W)     # 16:9 film (wider for a plate)
    cmds.setAttr(shape + ".filmFit", 1)                                # horizontal
    cmds.setAttr(shape + ".focalLength", focal)
    cmds.setAttr(shape + ".nearClipPlane", 0.1)
    cmds.setAttr(shape + ".farClipPlane", 3000)
    cmds.setAttr(cam + ".translate", 0, CAM_Y, z)
    return cam, shape


def make_cameras():
    """SHOT_CAM, and each plate camera on the same axis, farther back with a longer lens: at the layer's
    depth d it shows the same size (focal / distance equal), its film PLATE_SCALE times as wide."""
    cams = {"SHOT_CAM": _camera("SHOT_CAM", 35.0, CAM_Z)}
    for _layer, name, depth in PLATES:
        distance = depth * PLATE_FOCAL / 35.0
        cams[name] = _camera(name, PLATE_FOCAL, CAM_Z - depth + distance, film_scale=PLATE_SCALE)
    return cams


def _new_scene() -> bool:
    if cmds.file(q=True, modified=True):
        answer = cmds.confirmDialog(
            title="SyncBridge", message=u"保存されていない変更があります。新しいシーンにして、テスト用のシーンを作りますか？\n"
                                        u"（今のシーンの変更は失われます）",
            button=[u"新しいシーンにする", u"やめる"], defaultButton=u"やめる", cancelButton=u"やめる")
        if answer != u"新しいシーンにする":
            return False
    cmds.file(new=True, force=True)
    return True


def _syncbridge_layers(cams, groups):
    """Maya layers on their cameras (CHAR: SHOT_CAM, BOOK / BG: their plate cameras), new links in source
    camera mode, when the SyncBridge panel is loaded."""
    try:
        from syncbridge_maya import layer_mapping
    except ImportError:
        return u"SyncBridge のモジュールが読み込まれていないので、Maya レイヤーは作りませんでした（パネルを開いてから実行すると作ります）"
    camera_of = dict((layer, cam) for layer, cam, _ in PLATES)
    made = []
    for (name, _), grp in zip(LAYERS, groups):
        cam = cams[camera_of.get(name, "SHOT_CAM")][0]
        cmds.select(cam, grp, replace=True)
        layer, _warnings = layer_mapping.add_layer(name)
        made.append(u"%s（%s）" % (layer["name"], cam))
    cmds.select(clear=True)
    # AE layers of the same names added with "AE の選択を追加" are linked to these (D-43)
    return u"Maya レイヤーを作りました: %s。AE で同じ名前のレイヤーを「AE の選択を追加」すると、これにつながります" \
        % u"、".join(made)


def make_test_pan_scene():
    if not _new_scene():
        print(u"やめました（シーンは変えていません）。")
        return None
    cmds.setAttr("defaultResolution.width", W)
    cmds.setAttr("defaultResolution.height", H)
    cmds.setAttr("defaultResolution.deviceAspectRatio", float(W) / H)
    cmds.setAttr("defaultResolution.pixelAspect", 1.0)
    cmds.playbackOptions(minTime=START, maxTime=END, animationStartTime=START, animationEndTime=END)
    groups = [build_char(), build_book(), build_bg()]
    cams = make_cameras()
    shot = cams["SHOT_CAM"][1]
    for s in cmds.ls(type="camera", long=True):
        cmds.setAttr(s + ".renderable", s == shot)
    cmds.currentTime(START)
    note = _syncbridge_layers(cams, groups)
    if not cmds.about(batch=True):
        for panel in cmds.getPanel(visiblePanels=True) or []:
            if cmds.getPanel(typeOf=panel) == "modelPanel":
                cmds.modelEditor(panel, edit=True, displayTextures=True, displayAppearance="smoothShaded")
                cmds.lookThru(panel, cams["SHOT_CAM"][0])
                break
    print(u"横 PAN のテストシーンを作りました（カメラは固定）: 手前 PAN_CHAR（赤・その場歩き）、中景 PAN_BOOK（緑）、"
          u"奥 PAN_BG（青）。素材カメラ PLATE_BOOK_CAM / PLATE_BG_CAM（200mm・横 %d 倍）。%s" % (PLATE_SCALE, note))
    return {"cameras": cams, "groups": groups}


# -- the AE material ----------------------------------------------------------------------------------------
def _only(group):
    """lodVisibility off for every geometry shape outside `group` (not recorded for undo); returns them."""
    keep = set(cmds.listRelatives(group, allDescendents=True, type="geometryShape", fullPath=True) or [])
    hidden = []
    for shape in cmds.ls(type="geometryShape", long=True, noIntermediate=True) or []:
        plug = shape + ".lodVisibility"
        if shape in keep or not cmds.getAttr(plug) or cmds.getAttr(plug, lock=True) or \
                cmds.listConnections(plug, source=True, destination=False):
            continue
        cmds.setAttr(plug, False)
        hidden.append(shape)
    return hidden


def _render(camera_shape, width, height, path):
    cmds.setAttr("defaultResolution.width", width)
    cmds.setAttr("defaultResolution.height", height)
    cmds.setAttr("defaultResolution.deviceAspectRatio", float(width) / height)
    shutil.copyfile(cmds.ogsRender(camera=camera_shape, width=width, height=height), path)


def render_material(folder):
    """The BOOK / BG plates and the character's frames (Hardware 2.0, PNG with alpha) into `folder`.
    Everything changed for it is put back afterwards, outside the undo."""
    char_dir = os.path.join(folder, "char")
    if not os.path.isdir(char_dir):
        os.makedirs(char_dir)
    saved = {a: cmds.getAttr("defaultResolution." + a) for a in ("width", "height", "deviceAspectRatio")}
    saved_fmt = cmds.getAttr("defaultRenderGlobals.imageFormat")
    saved_prefix = cmds.getAttr("defaultRenderGlobals.imageFilePrefix") or ""
    saved_max = cmds.getAttr("hardwareRenderingGlobals.enableTextureMaxRes")
    saved_time = cmds.currentTime(q=True)
    undo_on = cmds.undoInfo(q=True, state=True)
    cmds.undoInfo(stateWithoutFlush=False)
    out = []
    try:
        cmds.setAttr("defaultRenderGlobals.imageFormat", 32)                     # PNG
        cmds.setAttr("defaultRenderGlobals.imageFilePrefix", "syncbridge_pan_test", type="string")
        cmds.setAttr("hardwareRenderingGlobals.enableTextureMaxRes", False)     # full-size textures
        cmds.currentTime(START)
        for layer, cam, _depth in PLATES:
            hidden = _only("PAN_" + layer)
            try:
                path = os.path.join(folder, "%s_plate_%dx%d.png" % (layer.lower(), W * PLATE_SCALE, H))
                _render(cmds.listRelatives(cam, shapes=True, fullPath=True)[0], W * PLATE_SCALE, H, path)
                out.append(path)
            finally:
                for shape in hidden:
                    cmds.setAttr(shape + ".lodVisibility", True)
        hidden = _only("PAN_CHAR")
        try:
            shot = cmds.listRelatives("SHOT_CAM", shapes=True, fullPath=True)[0]
            for frame in range(START, END + 1):
                cmds.currentTime(frame)
                _render(shot, W, H, os.path.join(char_dir, "char.%04d.png" % frame))
            out.append(os.path.join(char_dir, "char.%04d.png" % START))
        finally:
            for shape in hidden:
                cmds.setAttr(shape + ".lodVisibility", True)
    finally:
        for a, v in saved.items():
            cmds.setAttr("defaultResolution." + a, v)
        cmds.setAttr("defaultRenderGlobals.imageFormat", saved_fmt)
        cmds.setAttr("defaultRenderGlobals.imageFilePrefix", saved_prefix, type="string")
        cmds.setAttr("hardwareRenderingGlobals.enableTextureMaxRes", saved_max)
        cmds.currentTime(saved_time)
        cmds.undoInfo(stateWithoutFlush=undo_on)
    print(u"AE 用の素材を書き出しました: %s" % u"、".join(out))
    print(u"AE: 1920×1080 のコンポに 3 つを 100%% で中央に置き（上から CHAR、BOOK、BG）、BOOK は速く、BG はゆっくり左へ"
          u"スライドさせてください。CHAR は連番（char.0001.png〜）として読み込みます。")
    return out


def main():
    if make_test_pan_scene() is None:
        return
    answer = cmds.confirmDialog(title="SyncBridge", message=u"AE 用の素材（BOOK と BG の横長の 1 枚、キャラの連番 %d 枚）を"
                                u"書き出しますか？" % (END - START + 1),
                                button=[u"書き出す", u"あとで"], defaultButton=u"書き出す", cancelButton=u"あとで")
    if answer != u"書き出す":
        print(u"素材はあとで書き出せます: render_material(r\"書き出し先のフォルダ\")")
        return
    folders = cmds.fileDialog2(caption=u"AE 用の素材の書き出し先", fileMode=3,
                               startingDirectory=os.path.join(os.path.expanduser("~"), "Documents"))
    if folders:
        render_material(folders[0])


if __name__ == "__main__":
    main()
