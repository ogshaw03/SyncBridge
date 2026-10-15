import unittest

from syncbridge.core import testcurves
from syncbridge.core.curve import Extrapolation, Interp, Key, SampledCurve, TimeCurve

B, L, H = Interp.BEZIER, Interp.LINEAR, Interp.HOLD


class EvaluateTest(unittest.TestCase):
    def test_linear_segments(self):
        c = testcurves.slowmo_linear()
        self.assertAlmostEqual(c.evaluate(0.5), 0.5)
        self.assertAlmostEqual(c.evaluate(2.0), 1.5)   # 50% slow motion
        self.assertAlmostEqual(c.evaluate(3.5), 2.5)

    def test_constant_extrapolation(self):
        c = testcurves.slowmo_linear()
        self.assertEqual(c.evaluate(-1.0), 0.0)
        self.assertEqual(c.evaluate(10.0), 3.0)

    def test_linear_extrapolation(self):
        c = testcurves.linear_infinity()
        self.assertAlmostEqual(c.evaluate(0.0), 0.5)
        self.assertAlmostEqual(c.evaluate(3.0), 2.0)

    def test_hold_and_jump(self):
        c = testcurves.jump_hold()
        self.assertEqual(c.evaluate(1.0), 1.0)
        self.assertEqual(c.evaluate(1.999), 1.0)
        self.assertEqual(c.evaluate(2.0), 3.0)   # value at the key after the hold

    def test_reverse(self):
        c = testcurves.reverse()
        self.assertAlmostEqual(c.evaluate(1.5), 0.75)

    def test_bezier_with_third_handles_is_straight_when_collinear(self):
        c = TimeCurve([Key(0.0, 0.0, L, B, None, (1.0, 2.0)),
                       Key(3.0, 6.0, B, L, (-1.0, -2.0), None)])
        for t in (0.3, 1.0, 1.7, 2.9):
            self.assertAlmostEqual(c.evaluate(t), 2.0 * t, places=9)

    def test_bezier_endpoints_and_monotonic_ramp(self):
        c = testcurves.speed_ramp_bezier()
        self.assertAlmostEqual(c.evaluate(0.0), 0.0)
        self.assertAlmostEqual(c.evaluate(1.5), 3.0)
        self.assertAlmostEqual(c.evaluate(3.0), 6.0)
        vals = c.evaluate_many([i * 0.01 for i in range(301)])
        self.assertTrue(all(b >= a - 1e-12 for a, b in zip(vals, vals[1:])))

    def test_handles_clamped_to_segment(self):
        # Out handle longer than the segment must not break evaluation.
        c = TimeCurve([Key(0.0, 0.0, L, B, None, (5.0, 5.0)), Key(1.0, 1.0, B, L, (-0.1, 0.0))])
        for t in (0.0, 0.25, 0.5, 0.75, 1.0):
            v = c.evaluate(t)
            self.assertTrue(-1.0 < v < 2.0)

    def test_duplicate_key_times_rejected(self):
        with self.assertRaises(ValueError):
            TimeCurve([Key(1.0, 0.0), Key(1.0, 1.0)])

    def test_single_key(self):
        c = TimeCurve([Key(1.0, 5.0)])
        self.assertEqual(c.evaluate(0.0), 5.0)
        self.assertEqual(c.evaluate(9.0), 5.0)


class AffineTest(unittest.TestCase):
    def test_affine_is_exact_for_bezier(self):
        c = testcurves.asymmetric_ease()
        a = c.affine(in_scale=24.0, in_offset=1001.0, out_scale=24.0, out_offset=1001.0)
        for t in [i * 0.037 for i in range(82)]:
            self.assertAlmostEqual(a.evaluate(t * 24.0 + 1001.0), c.evaluate(t) * 24.0 + 1001.0, places=6)

    def test_affine_rejects_time_reversal(self):
        with self.assertRaises(ValueError):
            testcurves.identity().affine(in_scale=-1.0)


class JsonTest(unittest.TestCase):
    def test_roundtrip_all_reference_curves(self):
        for name, make in testcurves.CURVES.items():
            c = make()
            c2 = TimeCurve.from_json(c.to_json())
            for t in [i * 0.05 for i in range(-10, 100)]:
                self.assertAlmostEqual(c.evaluate(t), c2.evaluate(t), places=12, msg=name)

    def test_extrapolation_serialized(self):
        c = TimeCurve.from_json(testcurves.linear_infinity().to_json())
        self.assertEqual(c.pre_infinity, Extrapolation.LINEAR)


class SampledCurveTest(unittest.TestCase):
    def test_linear_interpolation_between_samples(self):
        s = SampledCurve([0.0, 1.0, 2.0], [0.0, 2.0, 2.0])
        self.assertAlmostEqual(s.evaluate(0.5), 1.0)
        self.assertEqual(s.evaluate(5.0), 2.0)


if __name__ == "__main__":
    unittest.main()
