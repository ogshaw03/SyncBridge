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
        self.assertEqual(len(pm.check_camera(camera(camera_scale=2.0, film_roll=5.0), RENDER)), 2)
        # 3:2 film with a 16:9 render: fill resolves to horizontal; vertical fit is not verified
        self.assertEqual(pm.check_camera(camera(vfa=0.945, film_fit=0), RENDER), [])
        self.assertEqual(len(pm.check_camera(camera(vfa=0.945, film_fit=2), RENDER)), 1)


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
