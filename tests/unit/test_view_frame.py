"""The viewer's comp frame (core.view_frame, D-34)."""
import unittest

from syncbridge.core.view_frame import frame_rect

CAM = {"hfa": 1.417, "vfa": 0.945, "film_fit": 1, "overscan": 1.0}
HD = {"width": 1920, "height": 1080, "pixel_aspect": 1.0}


class ViewFrameTest(unittest.TestCase):
    def assertRect(self, got, want):
        for g, w in zip(got, want):
            self.assertAlmostEqual(g, w, places=9)

    def test_render_aspect_view_is_filled(self):
        self.assertRect(frame_rect((0, 0, 1920, 1080), CAM, HD), (0.0, 0.0, 1920.0, 1080.0))

    def test_overscan_shrinks_around_the_center(self):
        l, b, r, t = frame_rect((10, 20, 1200, 600), dict(CAM, overscan=1.25), HD)
        l1, b1, r1, t1 = frame_rect((10, 20, 1200, 600), CAM, HD)
        self.assertAlmostEqual((r - l) * 1.25, r1 - l1)
        self.assertAlmostEqual((t - b) * 1.25, t1 - b1)
        self.assertAlmostEqual((l + r) / 2.0, 610.0)
        self.assertAlmostEqual((b + t) / 2.0, 320.0)

    def test_two_d_values_do_not_move_it(self):
        moved = dict(CAM, ft_h=0.3, hfo=0.1, hpan=0.2, film_roll=15.0, post_scale=1.4)
        self.assertEqual(frame_rect((0, 0, 1200, 600), moved, HD), frame_rect((0, 0, 1200, 600), CAM, HD))

    def test_comp_fraction(self):
        self.assertRect(frame_rect((0, 0, 1920, 1080), CAM, HD, {"width": 960, "height": 540}),
                        (480.0, 270.0, 1440.0, 810.0))


if __name__ == "__main__":
    unittest.main()
