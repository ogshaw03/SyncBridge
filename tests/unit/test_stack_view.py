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


class ViewerPanZoomTest(unittest.TestCase):
    """D-44: the viewer camera's own 2D pan / zoom are the view's; the editing camera's are folded."""

    CAMS = StackViewTest.CAMS
    POINTS = StackViewTest.POINTS
    VIEW = (1200, 700)

    def test_folding_keeps_the_picture(self):
        for camera in self.CAMS:
            a = sv.ndc_affine(camera, *self.VIEW)
            b = sv.ndc_affine(sv.fold_pan_zoom(camera), *self.VIEW)
            for p in self.POINTS:
                for x, y in zip(sv.apply_affine(a, p), sv.apply_affine(b, p)):
                    self.assertAlmostEqual(x, y)

    def test_no_view_pan_zoom_is_the_identity(self):
        for camera in self.CAMS:
            affine = sv.view_affine(camera, sv.with_view(camera, 0.0, 0.0, 1.0), *self.VIEW)
            for got, want in zip(affine, (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)):
                self.assertAlmostEqual(got, want)

    def test_other_layers_follow_the_view(self):
        # a layer drawn with view_affine o its own camera lands where the viewer camera puts the same point
        editing, other = self.CAMS[1], self.CAMS[2]
        viewer = sv.with_view(editing, 0.04, -0.01, 0.5)          # zoomed in 2x and panned
        va = sv.view_affine(editing, viewer, *self.VIEW)
        for p in self.POINTS:
            through_viewer = sv.apply_affine(sv.ndc_affine(viewer, *self.VIEW), p)
            through_editing = sv.map_point(va, sv.apply_affine(sv.ndc_affine(editing, *self.VIEW), p))
            for x, y in zip(through_viewer, through_editing):
                self.assertAlmostEqual(x, y)
        # zoom 0.5 doubles the distances on screen
        a, b = sv.map_point(va, (0.0, 0.0)), sv.map_point(va, (0.1, 0.0))
        self.assertAlmostEqual(abs(b[0] - a[0]), 0.2)
        layer_affine = sv.compose(va, sv.ndc_affine(other, *self.VIEW))
        self.assertIsNotNone(layer_affine)

    def test_the_view_stays_when_the_editing_layer_changes(self):
        # the pan / zoom for another camera that keeps the same view (the user saw it move, 2026-10-27)
        for before, after in ((self.CAMS[1], self.CAMS[2]), (self.CAMS[2], self.CAMS[0]),
                              (self.CAMS[0], self.CAMS[1])):
            view = sv.view_affine(before, sv.with_view(before, 0.03, -0.02, 0.6), *self.VIEW)
            hpan, vpan, zoom = sv.match_view(view, after, *self.VIEW)
            got = sv.view_affine(after, sv.with_view(after, hpan, vpan, zoom), *self.VIEW)
            for g, w in zip(got, view):
                self.assertAlmostEqual(g, w, places=9)
        # the same camera: the same numbers back
        camera = self.CAMS[2]
        view = sv.view_affine(camera, sv.with_view(camera, 0.05, 0.01, 1.3), *self.VIEW)
        for g, w in zip(sv.match_view(view, camera, *self.VIEW), (0.05, 0.01, 1.3)):
            self.assertAlmostEqual(g, w, places=9)

    def test_the_ray_goes_through_the_clicked_point(self):
        camera = self.CAMS[2]
        affine = sv.compose(sv.view_affine(camera, sv.with_view(camera, 0.02, 0.0, 0.7), *self.VIEW),
                            sv.ndc_affine(camera, *self.VIEW))
        for p in self.POINTS:
            ndc = sv.apply_affine(affine, p)
            u, v, w = sv.ray_direction(affine, ndc)
            self.assertAlmostEqual(u, p[0] / -p[2])
            self.assertAlmostEqual(v, p[1] / -p[2])
            self.assertEqual(w, -1.0)
        self.assertEqual(sv.pixel_to_ndc(600, 350, *self.VIEW), (0.0, 0.0))
        self.assertEqual(sv.pixel_to_ndc(0, 0, *self.VIEW), (-1.0, 1.0))
        for x, y in ((0, 0), (600, 350), (123.5, 700)):
            nx, ny = sv.pixel_to_ndc(x, y, *self.VIEW)
            gx, gy = sv.ndc_to_pixel((nx, ny), *self.VIEW)
            self.assertAlmostEqual(gx, x)
            self.assertAlmostEqual(gy, y)

    def test_distance_to_a_drawn_curve(self):
        square = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        self.assertAlmostEqual(sv.polyline_distance((5, -3), square), 3.0)       # off an edge
        self.assertAlmostEqual(sv.polyline_distance((13, 14), square), 5.0)      # off a corner
        self.assertAlmostEqual(sv.polyline_distance((5, 4), square), 4.0)        # inside: to the nearest edge
        self.assertAlmostEqual(sv.polyline_distance((7, 8), [(7, 8)]), 0.0)      # one point
        self.assertEqual(sv.polyline_distance((0, 0), []), float("inf"))


class SteadyViewTest(unittest.TestCase):
    """The viewer's view does not move with the editing layer's film translate / roll / post-scale keys
    (the user, 2026-10-29: the frame moved when the layer's motion was transferred)."""

    @staticmethod
    def editing(rng):
        return dict(focal_length=rng.uniform(20, 80), hfa=rng.uniform(0.8, 1.6), vfa=rng.uniform(0.5, 1.2),
                    film_fit=rng.choice([0, 1, 2, 3]), hfo=rng.uniform(-0.2, 0.2), vfo=rng.uniform(-0.2, 0.2),
                    pre_scale=rng.uniform(0.7, 1.4), post_scale=rng.uniform(0.6, 1.6), ft_h=rng.uniform(-0.5, 0.5),
                    ft_v=rng.uniform(-0.5, 0.5), film_roll=rng.uniform(-40, 40), roll_pivot_h=rng.uniform(-0.3, 0.3),
                    roll_pivot_v=rng.uniform(-0.3, 0.3), film_roll_order=rng.choice([0, 1]), overscan=1.0,
                    pan_zoom_enabled=rng.choice([False, True]), hpan=rng.uniform(-0.1, 0.1),
                    vpan=rng.uniform(-0.1, 0.1), zoom=rng.uniform(0.6, 1.5))

    def test_the_moving_view_before(self):
        # zoomed out (the margin), the frame's center moved by (1 - 1 / zoom) of the film translate
        ed = dict(base_cam(), ft_h=0.3)
        view = sv.view_affine(ed, sv.with_view(ed, 0.0, 0.0, 1.2), 1920, 1080)
        self.assertAlmostEqual(sv.map_point(view, (0.0, 0.0))[0], -0.05)

    def test_view_does_not_depend_on_the_motion(self):
        import random
        rng = random.Random(7)
        for _ in range(300):
            ed = self.editing(rng)
            w, h = rng.choice([(1920, 1080), (800, 900), (1200, 500)])
            viewer = sv.with_view(ed, rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), rng.uniform(0.5, 2.0))
            viewer["ft_h"], viewer["ft_v"] = sv.steady_translate(viewer, w / float(h))
            got = sv.view_affine(ed, viewer, w, h)
            want = sv.view_affine(sv.unmoved(ed), sv.unmoved(viewer), w, h)
            for a, b in zip(got, want):
                self.assertAlmostEqual(a, b, places=9)

    def test_no_view_no_change(self):
        ed = dict(base_cam(), ft_h=0.3, ft_v=-0.1, post_scale=1.3, film_roll=12.0)
        self.assertEqual(sv.steady_translate(sv.fold_pan_zoom(ed), 16 / 9.0), (0.3, -0.1))
        same = sv.steady_translate(sv.with_view(ed, 0.0, 0.0, 1.0), 16 / 9.0)
        self.assertAlmostEqual(same[0], 0.3)
        self.assertAlmostEqual(same[1], -0.1)


if __name__ == "__main__":
    unittest.main()
