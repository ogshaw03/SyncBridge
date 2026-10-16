import unittest
from fractions import Fraction

from syncbridge.core import maya_codec, testcurves, transfer
from syncbridge.core.mapping import MappingContext
from syncbridge.core.sampler import fit_precision
from syncbridge.core.validation import compare_curves, compare_samples

FPS = [24, 1]


class MappingTest(unittest.TestCase):
    def test_render_start_origin(self):
        # Maya frame 1001 -> comp 0 s; warped frame 1001 -> source 0 s.
        ctx = MappingContext(maya_fps=FPS, maya_input_origin_frame=1001, maya_output_origin_frame=1001)
        maya_s = testcurves.slowmo_linear().affine(in_offset=1001 / 24.0, out_offset=1001 / 24.0)
        ae = ctx.maya_to_ae(maya_s)
        self.assertAlmostEqual(ae.keys[0].t, 0.0, places=9)
        self.assertAlmostEqual(ae.keys[0].v, 0.0, places=9)
        self.assertAlmostEqual(ae.evaluate(2.0), 1.5, places=9)

    def test_inverse(self):
        ctx = MappingContext(maya_fps=[24000, 1001], maya_input_origin_frame=101,
                             maya_output_origin_frame=95, ae_comp_time_offset=2.5,
                             ae_source_time_offset=0.25, source_time_scale=24 / 25.0)
        c = testcurves.asymmetric_ease()
        back = ctx.ae_to_maya(ctx.maya_to_ae(c))
        rep = compare_curves(c, back, FPS, tolerance_frames=1e-6)
        self.assertTrue(rep.passed, rep.summary())


class PrecisionTest(unittest.TestCase):
    def test_all_curves_within_tolerance(self):
        for fps in (FPS, [24000, 1001], [30, 1]):
            for name, make in testcurves.CURVES.items():
                res = fit_precision(make(), fps, 0.1)
                self.assertTrue(res.report.passed, "%s @%s: %s" % (name, fps, res.report.summary()))
                for k in res.curve.keys:
                    self.assertIn(k.out_interp, ("linear", "hold"))

    def test_keys_are_reduced(self):
        res = fit_precision(testcurves.slowmo_linear(), FPS, 0.1)
        self.assertEqual(len(res.curve.keys), 4)   # already linear: no extra keys

    def test_hold_is_preserved_exactly(self):
        res = fit_precision(testcurves.jump_hold(), FPS, 0.1)
        self.assertEqual(res.curve.evaluate(1.5), 1.0)
        self.assertEqual(res.curve.evaluate(2.0), 3.0)

    def test_tighter_tolerance_uses_more_keys(self):
        loose = fit_precision(testcurves.speed_ramp_bezier(), FPS, 0.1)
        tight = fit_precision(testcurves.speed_ramp_bezier(), FPS, 0.01)
        self.assertTrue(tight.report.passed, tight.report.summary())
        self.assertGreater(len(tight.curve.keys), len(loose.curve.keys))

    def test_frame_aligned_keys_by_default(self):
        res = fit_precision(testcurves.speed_ramp_bezier(), FPS, 0.1, allow_subframe=False)
        for k in res.curve.keys:
            frames = k.t * 24
            self.assertAlmostEqual(frames, round(frames), places=6)

    def test_range_extension(self):
        res = fit_precision(testcurves.linear_infinity(), FPS, 0.1, t_range=(0.0, 3.0))
        self.assertAlmostEqual(res.curve.evaluate(0.0), 0.5, places=6)
        self.assertAlmostEqual(res.curve.evaluate(3.0), 2.0, places=6)


class TransferTest(unittest.TestCase):
    def setUp(self):
        self.ctx = MappingContext(maya_fps=FPS, maya_input_origin_frame=1001, maya_output_origin_frame=1001)

    def _maya_native(self, curve):
        return maya_codec.encode(curve.affine(in_offset=1001 / 24.0, out_offset=1001 / 24.0), FPS)

    def test_bidirectional_both_modes(self):
        for name, make in testcurves.CURVES.items():
            native = self._maya_native(make())
            for mode in transfer.MODES:
                to_ae = transfer.maya_to_ae(native, self.ctx, mode, 0.1, FPS)
                self.assertTrue(to_ae.passed, "%s %s: %s" % (name, mode, to_ae.conversion.summary()))
                to_maya = transfer.ae_to_maya(to_ae.native, self.ctx, mode, 0.1)
                self.assertTrue(to_maya.passed, name)
                # End to end: Maya -> AE -> Maya equals the original.
                original = maya_codec.decode(native)
                back = maya_codec.decode(to_maya.native)
                rep = compare_curves(original, back, FPS, 0.1)
                self.assertTrue(rep.passed, "%s %s roundtrip: %s" % (name, mode, rep.summary()))

    def test_source_fidelity_detects_wrong_tangent_assumption(self):
        native = self._maya_native(testcurves.speed_ramp_bezier())
        times = [k["time"] + 0.5 for k in native["keys"][:-1]]
        good = maya_codec.decode(native)
        values = [good.evaluate(t / 24.0) * 24.0 + 0.3 for t in times]   # Maya disagrees by 0.3 f
        res = transfer.maya_to_ae(native, self.ctx, transfer.EDITABLE, 0.1, FPS,
                                  maya_samples={"times": times, "values": values})
        self.assertFalse(res.source_fidelity.passed)
        self.assertFalse(res.passed)

    def test_ntsc_target(self):
        native = self._maya_native(testcurves.speed_ramp_bezier())
        res = transfer.maya_to_ae(native, self.ctx, transfer.PRECISION, 0.1, Fraction(24000, 1001))
        self.assertTrue(res.passed, res.conversion.summary())


class EvaluationRangeTest(unittest.TestCase):
    """R-20: Maya Scene Time Warps made in the UI use linear pre/post infinity."""

    def setUp(self):
        self.ctx = MappingContext(maya_fps=FPS, maya_input_origin_frame=1001, maya_output_origin_frame=1001)
        origin = 1001 / 24.0
        # Keys at 1 s and 2 s after the origin, linear infinity on both sides.
        self.native = maya_codec.encode(
            testcurves.linear_infinity().affine(in_offset=origin, out_offset=origin), FPS)
        self.range = (0.0, 3.0)   # comp seconds: 1 s before and after the keys

    def test_precision_bakes_extrapolation(self):
        res = transfer.maya_to_ae(self.native, self.ctx, transfer.PRECISION, 0.1, FPS, t_range=self.range)
        self.assertTrue(res.passed, res.conversion.summary())
        self.assertEqual(res.t_range, self.range)
        self.assertAlmostEqual(res.curve.evaluate(0.0), 0.5, delta=0.1 / 24)   # extrapolated, not held
        self.assertAlmostEqual(res.curve.evaluate(3.0), 2.0, delta=0.1 / 24)
        self.assertTrue(any("H-MY-11" in w for w in res.warnings), res.warnings)

    def test_conversion_report_covers_the_range(self):
        res = transfer.maya_to_ae(self.native, self.ctx, transfer.PRECISION, 0.1, FPS, t_range=self.range)
        self.assertGreaterEqual(res.conversion.sample_count, 3 * 24 * 8)

    def test_editable_reports_lost_extrapolation(self):
        res = transfer.maya_to_ae(self.native, self.ctx, transfer.EDITABLE, 0.1, FPS, t_range=self.range)
        self.assertFalse(res.passed)
        self.assertTrue(any("Precision" in w for w in res.warnings), res.warnings)

    def test_without_range_only_keys_must_match(self):
        res = transfer.maya_to_ae(self.native, self.ctx, transfer.EDITABLE, 0.1, FPS)
        self.assertTrue(res.passed, res.conversion.summary())
        self.assertIsNone(res.t_range)
        self.assertFalse(any("H-MY-11" in w for w in res.warnings))

    def test_constant_infinity_needs_no_baking(self):
        native = maya_codec.encode(testcurves.slowmo_linear().affine(in_offset=1001 / 24.0,
                                                                     out_offset=1001 / 24.0), FPS)
        for mode in transfer.MODES:
            res = transfer.maya_to_ae(native, self.ctx, mode, 0.1, FPS, t_range=(-1.0, 6.0))
            self.assertTrue(res.passed, "%s: %s" % (mode, res.conversion.summary()))
            self.assertFalse(any("H-MY-11" in w or "Editable" in w for w in res.warnings), res.warnings)

    def test_flat_linear_infinity_needs_no_warning(self):
        # Like a Scene Time Warp made in the Maya UI: linear infinity, 0-degree outer tangents.
        native = maya_codec.decode(self.native)
        native.keys[0].in_handle = (-1.0, 0.0)
        native.keys[-1].out_handle = (1.0, 0.0)
        flat = maya_codec.encode(native, FPS)
        res = transfer.maya_to_ae(flat, self.ctx, transfer.EDITABLE, 0.1, FPS, t_range=self.range)
        self.assertTrue(res.passed, res.conversion.summary())
        self.assertFalse(any("Editable" in w or "H-MY-11" in w for w in res.warnings), res.warnings)

    def test_ae_to_maya_with_range(self):
        to_ae = transfer.maya_to_ae(self.native, self.ctx, transfer.PRECISION, 0.1, FPS, t_range=self.range)
        maya_range = (1001 / 24.0 - 1.0, 1001 / 24.0 + 4.0)
        res = transfer.ae_to_maya(to_ae.native, self.ctx, transfer.PRECISION, 0.1, t_range=maya_range)
        self.assertTrue(res.passed, res.conversion.summary())
        self.assertEqual(res.native["preInfinity"], "constant")


class SourceRangeTest(unittest.TestCase):
    def test_output_range_includes_bezier_overshoot(self):
        from syncbridge.core import jobs
        lo, hi = jobs.output_range(testcurves.nonmonotonic_bezier(), FPS)
        self.assertGreater(hi, 1.0)        # the curve overshoots its last key value (1.0)
        self.assertAlmostEqual(lo, 0.0, places=6)


class ValidationTest(unittest.TestCase):
    def test_error_in_frames(self):
        rep = compare_samples([0.0, 1.0], [0.0, 1.0 + 0.5 / 24], lambda t: t, FPS, 0.1)
        self.assertAlmostEqual(rep.max_error_frames, 0.5)
        self.assertEqual(rep.worst_time, 1.0)
        self.assertFalse(rep.passed)
        self.assertEqual(rep.exceed_count, 1)


if __name__ == "__main__":
    unittest.main()
