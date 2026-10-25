"""Pixel Mapping Phase 3: the AE layer's motion as keys (core.motion, D-30)."""
import unittest

from syncbridge.core import layer_mapping as lm
from syncbridge.core import motion
from syncbridge.core import pixel_mapping as pm

from tests.unit.test_pixel_mapping import BG, COMP, RENDER, camera, ae_layer

AE = {"comp_id": 1, "comp": "c010", "layer_id": 5, "layer": "BG", "source": "bg", "source_width": 6000,
      "source_height": 4000}


def cam(**kw):
    return camera(hpan=0.0, vpan=0.0, zoom=1.0, pan_zoom_enabled=False, render_pan_zoom=False, hfo=0.0, vfo=0.0,
                  ft_h=0.0, ft_v=0.0, pre_scale=1.0, post_scale=1.0, film_roll=0.0, roll_pivot_h=0.0,
                  roll_pivot_v=0.0, film_roll_order=0, lens_squeeze=1.0, camera_scale=1.0, film_fit_offset=0.0,
                  overscan=1.0, **kw)


def relative_link(method="pan_zoom"):
    link = lm.new_mapping(AE, {"camera_uuid": "C"}, method=method, mode="relative")
    ref, _ = pm.ae_layer_matrix(ae_layer(960.0, 540.0))
    values = {k: cam()[k] for k in ("hpan", "vpan", "zoom", "pan_zoom_enabled", "render_pan_zoom", "ft_h", "ft_v",
                                    "post_scale", "film_roll")}
    return lm.with_reference(link, ref, values, 0.0)


class MotionTest(unittest.TestCase):
    def test_frame_times(self):
        frames = motion.frame_times(1001, 1004, 24, origin=1001)
        self.assertEqual([f for f, _ in frames], [1001.0, 1002.0, 1003.0, 1004.0])
        self.assertAlmostEqual(frames[3][1], 3 / 24.0)
        self.assertAlmostEqual(motion.frame_times(1, 2, "24000/1001", origin=0)[1][1], 2 * 1001 / 24000.0)
        with self.assertRaises(ValueError):
            motion.frame_times(10, 5, 24, 1)

    def test_every_frame_matches_a_single_send(self):
        link = relative_link()
        positions = [(960.0 + 8.0 * i, 540.0 - 3.5 * i) for i in range(6)]
        samples = [dict(ae_layer(x, y), t=i / 24.0) for i, (x, y) in enumerate(positions)]
        cameras = [cam(focal_length=35.0 + i) for i in range(6)]             # a zoom in the camera work
        result = motion.solve_motion(link, samples, cameras, RENDER, COMP)
        for sample, camera_now, values in zip(samples, cameras, result["values"]):
            m, _ = pm.ae_layer_matrix(sample)
            single = pm.solve_relative("pan_zoom", dict(camera_now, **link["reference"]["camera"]), RENDER, COMP,
                                       link["reference"]["matrix"], m)
            self.assertEqual(values, single["values"])
        self.assertLess(result["max_error_px"], 1e-6)
        keys, constant = motion.curves([1, 2, 3, 4, 5, 6], result["values"])
        self.assertEqual(sorted(keys), ["hpan", "vpan", "zoom"])
        self.assertEqual(constant, {"pan_zoom_enabled": True, "render_pan_zoom": True})
        self.assertEqual([f for f, _ in keys["hpan"]], [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        self.assertEqual(keys["hpan"][0][1], 0.0)                              # the reference frame: no change

    def test_absolute_mode(self):
        link = lm.new_mapping(AE, {"camera_uuid": "C", "bg_uuid": "B"}, method="film_offset", mode="absolute")
        samples = [ae_layer(1000.0 + i, 500.0) for i in range(3)]
        result = motion.solve_motion(link, samples, [cam()] * 3, RENDER, COMP, BG)
        self.assertEqual(len(result["values"]), 3)
        self.assertNotEqual(result["values"][0]["hfo"], result["values"][2]["hfo"])

    def test_refusals(self):
        no_ref = lm.new_mapping(AE, {"camera_uuid": "C"}, method="pan_zoom", mode="relative")
        with self.assertRaises(ValueError) as ctx:
            motion.solve_motion(no_ref, [ae_layer(960, 540)], [cam()], RENDER, COMP)
        self.assertIn(u"基準", str(ctx.exception))
        turned = [dict(ae_layer(960.0, 540.0), t=0.0), dict(ae_layer(960.0, 540.0), rotation=5.0, t=1 / 24.0)]
        with self.assertRaises(ValueError) as ctx:                             # pan_zoom cannot rotate
            motion.solve_motion(relative_link(), turned, [cam(), cam()], RENDER, COMP)
        self.assertIn(u"2 フレーム目", str(ctx.exception))
        result = motion.solve_motion(relative_link("film_roll"), turned, [cam(), cam()], RENDER, COMP)
        self.assertAlmostEqual(result["values"][1]["film_roll"], 5.0)


if __name__ == "__main__":
    unittest.main()
