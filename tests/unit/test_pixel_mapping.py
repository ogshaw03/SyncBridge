"""Pixel Mapping core: AE layer matrix, Maya camera model, solver (docs/PIXEL_MAPPING.md)."""
import math
import unittest

from syncbridge.core import pixel_mapping as pm

W, H = 1920, 1080
HFA = 1.417
RENDER = {"width": W, "height": H, "pixel_aspect": 1.0}
DIST = W * 35.0 / (HFA * 25.4)        # 1 world unit = 1 render pixel on the BG plane (the mayapy experiment)
BG = {"width": 6000, "height": 4000, "top_left": (-3000.0, 2000.0, 0.0), "top_right": (3000.0, 2000.0, 0.0),
      "bottom_left": (-3000.0, -2000.0, 0.0)}
COMP = {"width": W, "height": H, "pixelAspect": 1.0}


def camera(**kw):
    inv = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, -DIST, 1.0]
    cam = {"orthographic": False, "focal_length": 35.0, "hfa": HFA, "vfa": HFA * H / W, "film_fit": 1,
           "ortho_width": W, "world_inverse": inv}
    cam.update(kw)
    return cam


def ae_layer(x, y):
    return {"position": [x, y], "anchorPoint": [3000.0, 2000.0], "scale": [100.0, 100.0], "rotation": 0.0,
            "source": {"width": 6000, "height": 4000}}


class CameraModelTest(unittest.TestCase):
    """The formulas that the renders confirmed (mayapy 2024, 2026-10-24)."""

    def test_base_mapping(self):
        m = pm.maya_source_to_render(camera(), RENDER, BG)
        for sx, sy in ((0.5, 0.5), (3000.0, 2000.0), (5999.5, 3999.5)):
            x, y = pm.apply(m, sx, sy)
            self.assertAlmostEqual(x, sx - 2040.0, places=6)
            self.assertAlmostEqual(y, sy - 1460.0, places=6)

    def test_film_offset_translate_and_pan(self):
        px = HFA / W
        cases = [
            (camera(hfo=37 * px, vfo=-21 * px), (-37.0, -21.0)),
            (camera(ft_h=37.0 * 2 / W, ft_v=-21.0 * 2 / W), (-37.0, -21.0)),
            (camera(pan_zoom_enabled=True, render_pan_zoom=True, hpan=37 * px, vpan=-21 * px), (-37.0, -21.0)),
            (camera(pan_zoom_enabled=True, render_pan_zoom=False, hpan=37 * px), (0.0, 0.0)),
        ]
        for cam, (dx, dy) in cases:
            x, y = pm.apply(pm.maya_source_to_render(cam, RENDER, BG), 3000.0, 2000.0)
            self.assertAlmostEqual(x - 960.0, dx, places=6)
            self.assertAlmostEqual(y - 540.0, dy, places=6)

    def test_zoom_around_the_center(self):
        cam = camera(pan_zoom_enabled=True, render_pan_zoom=True, zoom=0.5)
        x, y = pm.apply(pm.maya_source_to_render(cam, RENDER, BG), 3100.0, 2000.0)
        self.assertAlmostEqual(x, 960.0 + 200.0)
        self.assertAlmostEqual(y, 540.0)

    def test_orthographic_ignores_film_offset_and_pan(self):
        inv = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, -1000.0, 1.0]
        ortho = camera(orthographic=True, world_inverse=inv, hfo=0.3,
                       pan_zoom_enabled=True, render_pan_zoom=True, hpan=0.2)
        self.assertAlmostEqual(pm.apply(pm.maya_source_to_render(ortho, RENDER, BG), 3000.0, 2000.0)[0], 960.0)
        ortho["ft_h"] = 0.1
        self.assertAlmostEqual(pm.apply(pm.maya_source_to_render(ortho, RENDER, BG), 3000.0, 2000.0)[0], 864.0)

    def test_tilted_plane_is_refused(self):
        tilted = dict(BG, top_right=(3000.0, 2000.0, -500.0))
        with self.assertRaises(ValueError):
            pm.maya_source_to_render(camera(), RENDER, tilted)

    def test_unsupported_camera_settings(self):
        self.assertEqual(pm.check_camera(camera(), RENDER), [])
        self.assertEqual(len(pm.check_camera(camera(camera_scale=2.0, film_fit_offset=0.1), RENDER)), 2)
        self.assertEqual(pm.check_camera(camera(film_roll=5.0, pre_scale=1.1, post_scale=0.9), RENDER), [])
        # 3:2 film with a 16:9 render: fill resolves to horizontal; vertical fit is not verified
        self.assertEqual(pm.check_camera(camera(vfa=0.945, film_fit=0), RENDER), [])
        self.assertEqual(len(pm.check_camera(camera(vfa=0.945, film_fit=2), RENDER)), 1)


class FilmTransformTest(unittest.TestCase):
    """Pre / Post Scale, Film Roll (pivot, order) and their order with zoom: what the renders showed
    (mayapy 2024, Hardware 2.0, 2026-10-25; H-PM-8). Shifts are of the image center, in render px."""

    def center_shift(self, **kw):
        x, y = pm.project(camera(**kw), RENDER, (0.0, 0.0, -DIST))
        return x - 960.0, y - 540.0

    def size(self, **kw):
        """(scale, angle in degrees, clockwise) of the picture: two points 100 px apart in the base view."""
        a = pm.project(camera(**kw), RENDER, (0.0, 0.0, -DIST))
        b = pm.project(camera(**kw), RENDER, (100.0, 0.0, -DIST))
        return math.hypot(b[0] - a[0], b[1] - a[1]) / 100.0, math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))

    def test_scales(self):
        self.assertAlmostEqual(self.size(pre_scale=1.05)[0], 1.05)
        self.assertAlmostEqual(self.size(post_scale=1.05)[0], 1.05)
        # film translate is not scaled by Pre Scale, but by Post Scale (measured -47.94 / -50.33)
        self.assertAlmostEqual(self.center_shift(pre_scale=1.05, ft_h=0.05)[0], -48.0)
        self.assertAlmostEqual(self.center_shift(post_scale=1.05, ft_h=0.05)[0], -50.4)
        # film offset / 2D pan come before Pre Scale (measured -71.20)
        self.assertAlmostEqual(self.center_shift(pre_scale=1.05, hfo=0.05)[0], -0.05 * W / HFA * 1.05)

    def test_roll(self):
        self.assertAlmostEqual(self.size(film_roll=3.0)[1], 3.0)             # clockwise on screen
        x, y = self.center_shift(film_roll=3.0, roll_pivot_h=0.1, roll_pivot_v=0.05)
        self.assertAlmostEqual(x, -2.38, places=2)                             # measured -2.368, -5.096
        self.assertAlmostEqual(y, -5.09, places=2)
        x, y = self.center_shift(film_roll=3.0, ft_h=0.05, film_roll_order=0)  # Rotate-Translate
        self.assertAlmostEqual((x, y), (-48.0, 0.0))
        x, y = self.center_shift(film_roll=3.0, ft_h=0.05, film_roll_order=1)  # Translate-Rotate
        self.assertAlmostEqual(x, -47.93, places=2)                            # measured -47.935, -2.516
        self.assertAlmostEqual(y, -2.51, places=2)
        x, y = self.center_shift(film_roll=3.0, hfo=0.05)                      # measured -67.662, -3.544
        self.assertAlmostEqual(x, -67.66, places=2)
        self.assertAlmostEqual(y, -3.55, places=2)

    def test_zoom_comes_before_film_translate(self):
        pz = {"pan_zoom_enabled": True, "render_pan_zoom": True}
        self.assertAlmostEqual(self.center_shift(zoom=0.95, ft_h=0.05, **pz)[0], -48.0)   # measured -48.014
        self.assertAlmostEqual(self.size(zoom=0.95, **pz)[0], 1 / 0.95)
        x, y = self.center_shift(zoom=0.95, film_roll=3.0, roll_pivot_h=0.1, **pz)        # measured +0.132, -5.021
        self.assertAlmostEqual(x, 0.13, places=2)
        self.assertAlmostEqual(y, -5.02, places=2)


class AeLayerTest(unittest.TestCase):
    def test_position_and_anchor(self):
        m, warnings = pm.ae_layer_matrix(ae_layer(960.0, 540.0))
        self.assertEqual(warnings, [])
        self.assertEqual(pm.apply(m, 3000.0, 2000.0), (960.0, 540.0))
        self.assertEqual(pm.apply(m, 0.0, 0.0), (-2040.0, -1460.0))

    def test_scale_and_rotation(self):
        layer = dict(ae_layer(960.0, 540.0), scale=[50.0, 50.0], rotation=90.0)
        m, warnings = pm.ae_layer_matrix(layer)
        self.assertEqual(len(warnings), 2)
        x, y = pm.apply(m, 3100.0, 2000.0)              # 100 px right of the anchor -> 50 px down
        self.assertAlmostEqual(x, 960.0)
        self.assertAlmostEqual(y, 590.0)

    def test_unsupported_layers(self):
        for extra in ({"threeD": True}, {"parent": "Null 1"}, {"effects": ["Transform"]}):
            with self.assertRaises(ValueError):
                pm.ae_layer_matrix(dict(ae_layer(0, 0), **extra))


class SolverTest(unittest.TestCase):
    def test_default_position_needs_no_offset(self):
        m, _ = pm.ae_layer_matrix(ae_layer(960.0, 540.0))
        r = pm.solve("film_offset", camera(), RENDER, BG, m, COMP)
        self.assertAlmostEqual(r["values"]["hfo"], 0.0)
        self.assertAlmostEqual(r["values"]["vfo"], 0.0)

    def test_each_method_reproduces_the_ae_position(self):
        m, _ = pm.ae_layer_matrix(ae_layer(960.0 + 123.25, 540.0 - 47.5))       # sub-pixel slide
        for method in pm.METHODS:
            r = pm.solve(method, camera(), RENDER, BG, m, COMP)
            self.assertLess(r["max_error_px"], 1e-6, method)
            self.assertAlmostEqual(r["shift_px"][0], 123.25)
            self.assertAlmostEqual(r["shift_px"][1], -47.5)
        r = pm.solve("film_offset", camera(), RENDER, BG, m, COMP)
        self.assertAlmostEqual(r["values"]["hfo"], -123.25 * HFA / W)
        self.assertAlmostEqual(r["values"]["vfo"], -47.5 * HFA / W)

    def test_small_size_differences_are_judged_in_pixels(self):
        # 2026-10-25: the user typed the camera distance as 18.670 (exact 18.67092): 0.005 % larger
        m, _ = pm.ae_layer_matrix(ae_layer(960.0 + 500.0, 540.0))
        typed = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, -18.670, 1.0]
        scale = DIST / 18.670                                    # the plane is 1 unit = 1 px at DIST
        cam = camera(world_inverse=typed)
        bg = {"width": 6000, "height": 4000, "top_left": (-3000.0 / scale, 2000.0 / scale, 0.0),
              "top_right": (3000.0 / scale, 2000.0 / scale, 0.0), "bottom_left": (-3000.0 / scale, -2000.0 / scale, 0.0)}
        # this test's plane and camera are scaled together: exact. Now nudge the distance like the user did
        bg_user = {"width": 6000, "height": 4000, "top_left": (-30.0, 20.0, 0.0), "top_right": (30.0, 20.0, 0.0),
                   "bottom_left": (-30.0, -20.0, 0.0)}
        r = pm.solve("film_offset", cam, RENDER, bg_user, m, COMP)
        self.assertLess(r["max_error_px"], 0.1)
        self.assertEqual(r["warnings"], [])
        self.assertLess(pm.solve("film_offset", cam, RENDER, bg, m, COMP)["max_error_px"], 1e-6)
        # 0.03 % larger: about 0.3 px at the corners -> applied with a warning
        near = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, -18.665, 1.0]
        r = pm.solve("film_offset", camera(world_inverse=near), RENDER, bg_user, m, COMP)
        self.assertTrue(0.1 <= r["max_error_px"] < 1.0, r["max_error_px"])
        self.assertEqual(len(r["warnings"]), 1)
        # the comp center is exact whatever the size difference
        far = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, -18.60, 1.0]
        with self.assertRaises(ValueError):
            pm.solve("film_offset", camera(world_inverse=far), RENDER, bg_user, m, COMP)

    def test_pan_with_a_zoomed_camera_is_refused(self):
        m, _ = pm.ae_layer_matrix(ae_layer(1000.0, 500.0))
        with self.assertRaises(ValueError):
            pm.solve("pan_zoom", camera(zoom=0.5), RENDER, BG, m, COMP)

    def test_mismatches_are_refused(self):
        m, _ = pm.ae_layer_matrix(ae_layer(1000.0, 500.0))
        with self.assertRaises(ValueError):          # comp size
            pm.solve("film_offset", camera(), RENDER, BG, m, {"width": 1280, "height": 720})
        with self.assertRaises(ValueError):          # BG shown at another size
            pm.solve("film_offset", camera(focal_length=50.0), RENDER, BG, m, COMP)
        inv = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, -1000.0, 1.0]
        with self.assertRaises(ValueError):          # orthographic ignores film offset
            pm.solve("film_offset", camera(orthographic=True, world_inverse=inv), RENDER, BG, m, COMP)
        r = pm.solve("film_translate", camera(orthographic=True, world_inverse=inv), RENDER, BG, m, COMP)
        self.assertLess(r["max_error_px"], 1e-6)


class RelativeModeTest(unittest.TestCase):
    """Phase 2.5 (D-25): no BG geometry, the AE BG's 2D change from the reference on top of the camera."""

    def matrices(self, ref, cur, scale=100.0, rotation=0.0):
        r, _ = pm.ae_layer_matrix(ae_layer(*ref))
        c, _ = pm.ae_layer_matrix(dict(ae_layer(*cur), scale=[scale, scale], rotation=rotation))
        return r, c

    def check_picture_moved(self, cam, values, change):
        """Every frame point moved exactly by the AE change (whatever its depth)."""
        moved = dict(cam, **values)
        for p in pm._frame_points(cam, RENDER) + [(5.0, -3.0, -40.0), (-200.0, 90.0, -900.0)]:
            before = pm.project(cam, RENDER, p)
            after = pm.project(moved, RENDER, p)
            want = pm.apply(change, *before)
            self.assertAlmostEqual(after[0], want[0], places=6)
            self.assertAlmostEqual(after[1], want[1], places=6)

    def test_slide_with_each_method(self):
        ref, cur = self.matrices((960.0, 540.0), (1060.25, 500.0))
        change = pm.multiply(cur, pm.invert(ref))
        for method in pm.METHODS:
            r = pm.solve_relative(method, camera(), RENDER, COMP, ref, cur)
            self.assertLess(r["max_error_px"], 1e-6, method)
            self.assertAlmostEqual(r["change"]["dx"], 100.25)
            self.assertAlmostEqual(r["change"]["dy"], -40.0)
            self.check_picture_moved(camera(), r["values"], change)
        r = pm.solve_relative("film_offset", camera(), RENDER, COMP, ref, cur)
        self.assertAlmostEqual(r["values"]["hfo"], -100.25 * HFA / W)
        self.assertAlmostEqual(r["values"]["vfo"], -40.0 * HFA / W)

    def test_added_to_the_camera_work(self):
        # the camera has its own film offset (camera work) and an earlier 2D pan: only the pan changes
        cam = camera(hfo=0.2, vfo=-0.1, pan_zoom_enabled=True, render_pan_zoom=True, hpan=0.05, vpan=0.01)
        ref, cur = self.matrices((960.0, 540.0), (900.0, 600.0))
        r = pm.solve_relative("pan_zoom", cam, RENDER, COMP, ref, cur)
        self.assertNotIn("hfo", r["values"])
        self.assertAlmostEqual(r["values"]["hpan"], 0.05 + 60.0 * HFA / W)
        self.assertAlmostEqual(r["values"]["vpan"], 0.01 + 60.0 * HFA / W)
        self.check_picture_moved(cam, r["values"], pm.multiply(cur, pm.invert(ref)))

    def test_scale_needs_pan_zoom(self):
        ref, cur = self.matrices((960.0, 540.0), (1000.0, 520.0), scale=110.0)
        r = pm.solve_relative("pan_zoom", camera(), RENDER, COMP, ref, cur)
        self.assertLess(r["max_error_px"], 1e-6)
        self.assertAlmostEqual(r["values"]["zoom"], 1.0 / 1.1)
        self.assertAlmostEqual(r["change"]["scale"], 1.1)
        self.check_picture_moved(camera(), r["values"], pm.multiply(cur, pm.invert(ref)))
        with self.assertRaises(ValueError):
            pm.solve_relative("film_offset", camera(), RENDER, COMP, ref, cur)

    def test_overscan_of_a_playblast(self):
        # 2026-10-25: the user's cameras have overscan 1.3 and the AE footage is a playblast with it.
        # Renders ignore overscan (measured); in the playblast the picture is 1 / 1.3 the size, so the
        # same AE slide needs 1.3 times the offset.
        ref, cur = self.matrices((960.0, 540.0), (1060.0, 540.0))
        plain = pm.solve_relative("film_roll", camera(overscan=1.3), RENDER, COMP, ref, cur)   # render image
        play = pm.solve_relative("film_roll", camera(overscan=1.3, view_overscan=True), RENDER, COMP, ref, cur)
        self.assertAlmostEqual(play["values"]["ft_h"], plain["values"]["ft_h"] * 1.3)
        self.check_picture_moved(camera(overscan=1.3, view_overscan=True), play["values"],
                                 pm.multiply(cur, pm.invert(ref)))
        self.assertEqual(pm.check_camera(camera(overscan=1.3), RENDER), [])
        # rotation and scale are the same in both
        _, cur = self.matrices((960.0, 540.0), (960.0, 540.0), scale=150.0, rotation=20.0)
        play = pm.solve_relative("film_roll", camera(overscan=1.3, view_overscan=True), RENDER, COMP, ref, cur)
        self.assertAlmostEqual(play["values"]["film_roll"], 20.0)
        self.assertAlmostEqual(play["values"]["post_scale"], 1.5)

    def test_film_roll_method_shows_rotation_and_scale(self):
        # the user's cases (2026-10-25): 42 degrees and 170 %, refused by the other methods
        ref, _ = self.matrices((960.0, 540.0), (960.0, 540.0))
        for cam in (camera(), camera(roll_pivot_h=0.2, roll_pivot_v=-0.1, film_roll_order=1, post_scale=0.9,
                                     pre_scale=1.1, film_roll=5.0, hfo=0.03)):
            for pos, scale, rot in (((1100.0, 400.0), 100.0, 42.0), ((900.0, 600.0), 170.0, 0.0),
                                    ((1000.0, 520.0), 170.0, 42.0), ((960.0, 540.0), 80.0, -15.5)):
                _, cur = self.matrices((960.0, 540.0), pos, scale=scale, rotation=rot)
                r = pm.solve_relative("film_roll", cam, RENDER, COMP, ref, cur)
                self.assertLess(r["max_error_px"], 1e-6, (pos, scale, rot))
                self.assertAlmostEqual(r["change"]["rotation"], rot)
                self.assertAlmostEqual(r["values"]["film_roll"], cam.get("film_roll", 0.0) + rot)
                self.assertAlmostEqual(r["values"]["post_scale"], cam.get("post_scale", 1.0) * scale / 100.0)
                self.check_picture_moved(cam, r["values"], pm.multiply(cur, pm.invert(ref)))
        _, cur = self.matrices((960.0, 540.0), (960.0, 540.0), rotation=42.0)
        with self.assertRaises(ValueError) as ctx:
            pm.solve_relative("pan_zoom", camera(), RENDER, COMP, ref, cur)
        self.assertIn(u"Film Translate・Scale・Roll", str(ctx.exception))

    def test_rotation_and_orthographic(self):
        ref, cur = self.matrices((960.0, 540.0), (960.0, 540.0), rotation=2.0)
        with self.assertRaises(ValueError):
            pm.solve_relative("pan_zoom", camera(), RENDER, COMP, ref, cur)
        inv = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, -1000.0, 1.0]
        ortho = camera(orthographic=True, world_inverse=inv)
        ref, cur = self.matrices((960.0, 540.0), (1000.0, 540.0))
        r = pm.solve_relative("film_translate", ortho, RENDER, COMP, ref, cur)
        self.assertLess(r["max_error_px"], 1e-6)
        with self.assertRaises(ValueError):
            pm.solve_relative("pan_zoom", ortho, RENDER, COMP, ref, cur)


if __name__ == "__main__":
    unittest.main()
