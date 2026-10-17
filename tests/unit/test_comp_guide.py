"""Comp guide math (D-16): resolution gate fit and the comp frame inside it."""
import unittest

from syncbridge.core import comp_guide as cg

# Maya's default camera: 35 mm focal length, 1.417 x 0.945 in film back (36 x 24 mm).
CAM = {"orthographic": False, "focal_length": 35.0, "h_aperture": 36 / 25.4, "v_aperture": 24 / 25.4,
       "h_offset": 0.0, "v_offset": 0.0, "film_fit": cg.FIT_FILL}
HD = {"width": 1920, "height": 1080, "device_aspect": 1920 / 1080.0, "pixel_aspect": 1.0}


def comp(w, h, pa=1.0, name="comp"):
    return cg.parse_comp({"name": name, "width": w, "height": h, "pixelAspect": pa})


class ParseTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(comp(1920, 1080), {"name": "comp", "width": 1920, "height": 1080, "pixel_aspect": 1.0})
        self.assertEqual(cg.parse_comp({"width": "100", "height": 50})["pixel_aspect"], 1.0)
        for bad in (None, {}, {"width": 0, "height": 10}, {"width": "x", "height": 1},
                    {"width": 1, "height": 1, "pixelAspect": "wide"}):
            with self.assertRaises(ValueError):
                cg.parse_comp(bad)


class GateTest(unittest.TestCase):
    FILM = (36 / 25.4, 24 / 25.4)    # aspect 1.5

    def gate(self, fit, aspect):
        return cg.resolution_gate(fit, self.FILM[0], self.FILM[1], aspect)

    def test_horizontal_and_vertical(self):
        w, h = self.gate(cg.FIT_HORIZONTAL, 16 / 9.0)
        self.assertAlmostEqual(w, 36.0, places=3)
        self.assertAlmostEqual(h, 36.0 * 9 / 16, places=3)
        w, h = self.gate(cg.FIT_VERTICAL, 16 / 9.0)
        self.assertAlmostEqual(h, 24.0, places=3)
        self.assertAlmostEqual(w, 24.0 * 16 / 9, places=3)

    def test_fill_stays_inside_the_film_gate(self):
        for aspect in (16 / 9.0, 4 / 3.0, 1.0, 2.39):
            w, h = self.gate(cg.FIT_FILL, aspect)
            self.assertLessEqual(w, 36.0 + 1e-6)
            self.assertLessEqual(h, 24.0 + 1e-6)
            self.assertTrue(abs(w - 36.0) < 1e-3 or abs(h - 24.0) < 1e-3)
            self.assertAlmostEqual(w / h, aspect, places=6)

    def test_overscan_contains_the_film_gate(self):
        for aspect in (16 / 9.0, 4 / 3.0, 1.0):
            w, h = self.gate(cg.FIT_OVERSCAN, aspect)
            self.assertGreaterEqual(w, 36.0 - 1e-6)
            self.assertGreaterEqual(h, 24.0 - 1e-6)
            self.assertAlmostEqual(w / h, aspect, places=6)

    def test_bad_values(self):
        with self.assertRaises(ValueError):
            cg.resolution_gate(cg.FIT_FILL, 0, 1, 1)
        with self.assertRaises(ValueError):
            cg.resolution_gate(7, 1, 1, 1)


class RectTest(unittest.TestCase):
    def test_same_size_comp_is_the_resolution_gate(self):
        # The check to run in Maya: a comp as large as the render must lie on the resolution gate.
        r = cg.guide_rect(CAM, HD, comp(1920, 1080), distance=10.0)
        half_w, half_h = r["gate"]
        self.assertEqual(r["fraction"], (1.0, 1.0))
        self.assertEqual(r["corners"][0], (-half_w, -half_h, -10.0))
        self.assertEqual(r["corners"][2], (half_w, half_h, -10.0))
        self.assertAlmostEqual(half_w, 36.0 / 2 * 10 / 35.0, places=6)   # 16:9 is wider than 3:2: horizontal

    def test_margin_render_gives_a_smaller_centred_frame(self):
        render = {"width": 2112, "height": 1188, "device_aspect": 2112 / 1188.0}
        r = cg.guide_rect(CAM, render, comp(1920, 1080), distance=1.0)
        fx, fy = r["fraction"]
        self.assertAlmostEqual(fx, 1920 / 2112.0)
        self.assertAlmostEqual(fy, 1080 / 1188.0)
        xs = [c[0] for c in r["corners"]]
        self.assertAlmostEqual(min(xs), -max(xs))
        self.assertAlmostEqual(max(xs), r["gate"][0] * fx)

    def test_distance_scales_perspective_only(self):
        a = cg.guide_rect(CAM, HD, comp(1920, 1080), 1.0)["gate"]
        b = cg.guide_rect(CAM, HD, comp(1920, 1080), 3.0)["gate"]
        self.assertAlmostEqual(b[0], 3 * a[0])
        ortho = dict(CAM, orthographic=True, orthographic_width=30.0)
        c = cg.guide_rect(ortho, HD, comp(1920, 1080), 1.0)["gate"]
        d = cg.guide_rect(ortho, HD, comp(1920, 1080), 3.0)["gate"]
        self.assertEqual(c, d)
        self.assertAlmostEqual(c[0] * 2, 30.0)        # horizontal fit: the full ortho width

    def test_film_offset_moves_the_frame(self):
        cam = dict(CAM, h_offset=0.1)
        r = cg.guide_rect(cam, HD, comp(1920, 1080), 35.0)
        xs = [c[0] for c in r["corners"]]
        self.assertAlmostEqual((min(xs) + max(xs)) / 2, 2.54)

    def test_draw_distance_between_clip_planes(self):
        self.assertEqual(cg.draw_distance(0.1, 10000), 0.2)
        self.assertAlmostEqual(cg.draw_distance(1.0, 1.5), 1.25)
        self.assertGreater(cg.draw_distance(0, 100), 0)


class WarningTest(unittest.TestCase):
    def test_no_warnings_for_a_normal_setup(self):
        self.assertEqual(cg.warnings(CAM, HD, comp(1920, 1080)), [])

    def test_warnings(self):
        out = cg.warnings(dict(CAM, lens_squeeze=2.0, film_translate_h=0.1), HD, comp(2048, 1080, pa=2.0))
        self.assertEqual(len(out), 3)
        self.assertIn(u"はみ出します", out[0])
        self.assertIn(u"ピクセル縦横比", out[1])
        self.assertIn("Lens Squeeze Ratio=2", out[2])
        self.assertIn("Film Translate H=0.1", out[2])

    def test_label(self):
        self.assertEqual(cg.label(comp(1920, 1080, name="AE main"), HD), "AE main 1920x1080 / Maya 1920x1080")
        self.assertEqual(cg.label(comp(1280, 720, name=""), HD), "1280x720 / Maya 1920x1080")   # typed in Maya


if __name__ == "__main__":
    unittest.main()
