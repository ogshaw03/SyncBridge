"""The viewer's margin (core.stack_view, D-34)."""
import unittest

from syncbridge.core import pixel_mapping as pm
from syncbridge.core import stack_view as sv

from tests.unit.test_motion import cam as base_cam


def cam(**kw):
    return dict(base_cam(), **kw)


def clip(m, p):
    x, y, z = p
    row = (x, y, z, 1.0)
    return [sum(row[i] * m[i * 4 + j] for i in range(4)) for j in range(4)]


class StackViewTest(unittest.TestCase):
    CAMS = [cam(), cam(hpan=0.03, vpan=-0.02, zoom=0.8, pan_zoom_enabled=True, hfo=0.01),
            cam(ft_h=0.1, ft_v=-0.05, post_scale=1.2, film_roll=12.0, pre_scale=0.9, overscan=1.3),
            cam(film_fit=2, focal_length=50.0)]
    POINTS = [(0.3, -0.2, -2.0), (-1.5, 0.7, -9.0), (0.0, 0.0, -1.0), (4.0, 2.5, -30.0)]

    def test_affine_is_the_camera_model(self):
        for camera in self.CAMS:
            for view in ((1920, 1080), (1200, 700), (800, 900)):
                affine = sv.ndc_affine(camera, view[0], view[1])
                model = sv.view_camera(camera)
                render = {"width": view[0], "height": view[1], "pixel_aspect": 1.0}
                for p in self.POINTS:
                    px, py = pm.project(model, render, p)
                    nx, ny = sv.apply_affine(affine, p)
                    self.assertAlmostEqual((nx + 1.0) * 0.5 * view[0], px, places=6)
                    self.assertAlmostEqual((1.0 - ny) * 0.5 * view[1], py, places=6)

    def test_margin_shrinks_around_the_center(self):
        camera = self.CAMS[1]
        a1 = sv.ndc_affine(camera, 1200, 700)
        a2 = sv.ndc_affine(camera, 1200, 700, margin=1.25)
        for p in self.POINTS:
            n1, n2 = sv.apply_affine(a1, p), sv.apply_affine(a2, p)
            self.assertAlmostEqual(n2[0], n1[0] / 1.25)
            self.assertAlmostEqual(n2[1], n1[1] / 1.25)

    def test_projection_matrix_gives_the_affine(self):
        affine = sv.ndc_affine(self.CAMS[2], 1200, 700, margin=1.2)
        for depth in (None, [(0.0, 0.0), (0.0, 0.0), (-1.0002, -1.0), (-0.20002, 0.0)],      # OpenGL
                      [(0.0, 0.0), (0.0, 0.0), (1.00001, 1.0), (-0.100001, 0.0)]):          # w = +z
            m = sv.projection_rows(affine, depth)
            for p in self.POINTS:
                x, y, z, w = clip(m, p)
                nx, ny = sv.apply_affine(affine, p)
                self.assertAlmostEqual(x / w, nx)
                self.assertAlmostEqual(y / w, ny)
        with self.assertRaises(ValueError):
            sv.projection_rows(affine, [(0.0, 0.0), (0.0, 0.0), (-1.0, 0.0), (0.0, 1.0)])   # orthographic
        with self.assertRaises(ValueError):
            sv.ndc_affine(cam(orthographic=True, ortho_width=30.0), 100, 100)


if __name__ == "__main__":
    unittest.main()
