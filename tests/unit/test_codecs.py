import unittest

from syncbridge.core import ae_codec, maya_codec, testcurves
from syncbridge.core.ae_codec import EncodeReport
from syncbridge.core.curve import Interp, Key, TimeCurve
from syncbridge.core.validation import compare_curves

FPS = [24, 1]


def assert_same(test, a, b, tol=1e-6, msg=None):
    rep = compare_curves(a, b, FPS, tolerance_frames=tol, oversample=16)
    test.assertTrue(rep.passed, "%s: %s" % (msg, rep.summary()))


class AECodecTest(unittest.TestCase):
    def test_roundtrip_all_reference_curves(self):
        for name, make in testcurves.CURVES.items():
            c = make()
            report = EncodeReport()
            assert_same(self, c, ae_codec.decode(ae_codec.encode(c, report)), msg=name)
            self.assertTrue(report.lossless, "%s: %s" % (name, report.warnings))

    def test_ease_to_handle_formula(self):
        # H-AE-3: influence 50% of a 2 s segment, speed 1.5 -> handle (1.0, 1.5)
        keys = [
            {"time": 0.0, "value": 0.0, "inInterp": "LINEAR", "outInterp": "BEZIER",
             "outEase": {"speed": 1.5, "influence": 50.0}},
            {"time": 2.0, "value": 2.0, "inInterp": "BEZIER", "outInterp": "LINEAR",
             "inEase": {"speed": 0.5, "influence": 25.0}},
        ]
        c = ae_codec.decode(keys)
        p0, p1, p2, p3 = c.segment_bezier(0)
        self.assertAlmostEqual(p1[0], 1.0)
        self.assertAlmostEqual(p1[1], 1.5)
        self.assertAlmostEqual(p2[0], 1.5)    # 2.0 - 0.25 * 2
        self.assertAlmostEqual(p2[1], 1.75)   # 2.0 - 0.5 * 0.5

    def test_encode_produces_ae_fields(self):
        keys = ae_codec.encode(testcurves.speed_ramp_bezier())
        self.assertEqual(keys[0]["outInterp"], "BEZIER")
        self.assertAlmostEqual(keys[0]["outEase"]["influence"], 100.0 / 3.0)
        self.assertAlmostEqual(keys[0]["outEase"]["speed"], 1.0)
        self.assertAlmostEqual(keys[1]["inEase"]["speed"], 3.0)

    def test_hold_maps_to_hold(self):
        keys = ae_codec.encode(testcurves.freeze_hold())
        self.assertEqual(keys[1]["outInterp"], "HOLD")

    def test_tiny_influence_is_clamped_and_reported(self):
        c = TimeCurve([Key(0.0, 0.0, Interp.LINEAR, Interp.BEZIER, None, (0.00001, 0.0)),
                       Key(1.0, 1.0)])
        report = EncodeReport()
        keys = ae_codec.encode(c, report)
        self.assertEqual(keys[0]["outEase"]["influence"], ae_codec.AE_MIN_INFLUENCE)
        self.assertFalse(report.lossless)

    def test_linear_infinity_reported(self):
        report = EncodeReport()
        ae_codec.encode(testcurves.linear_infinity(), report)
        self.assertFalse(report.lossless)


class MayaCodecTest(unittest.TestCase):
    def test_roundtrip_all_reference_curves(self):
        for name, make in list(testcurves.CURVES.items()) + [("linear_infinity", testcurves.linear_infinity)]:
            c = make()
            report = EncodeReport()
            native = maya_codec.encode(c, FPS, report)
            assert_same(self, c, maya_codec.decode(native), msg=name)
            self.assertTrue(report.lossless, "%s: %s" % (name, report.warnings))

    def test_units_are_frames(self):
        native = maya_codec.encode(testcurves.slowmo_linear(), FPS)
        self.assertEqual([k["time"] for k in native["keys"]], [0.0, 24.0, 72.0, 96.0])
        self.assertEqual(native["keys"][2]["value"], 48.0)

    def test_non_weighted_when_handles_are_thirds(self):
        self.assertFalse(maya_codec.encode(testcurves.speed_ramp_bezier(), FPS)["weighted"])
        self.assertTrue(maya_codec.encode(testcurves.asymmetric_ease(), FPS)["weighted"])

    def test_step_and_linear_types(self):
        native = maya_codec.encode(testcurves.freeze_hold(), FPS)
        self.assertEqual(native["keys"][1]["outTangentType"], "step")
        self.assertEqual(native["keys"][0]["outTangentType"], "linear")

    def test_decode_hermite_slopes(self):
        # Non-weighted Maya segment = Hermite: slope 0 at both ends -> ease in/out, midpoint is half.
        native = {"fps": FPS, "weighted": False, "keys": [
            {"time": 0, "value": 0, "inTangentType": "fixed", "outTangentType": "fixed",
             "inSlope": 0.0, "outSlope": 0.0},
            {"time": 48, "value": 24, "inTangentType": "fixed", "outTangentType": "fixed",
             "inSlope": 0.0, "outSlope": 0.0},
        ]}
        c = maya_codec.decode(native)
        self.assertAlmostEqual(c.evaluate(1.0), 0.5, places=9)   # seconds
        self.assertLess(c.evaluate(0.25), 0.25 * 0.5)            # slow start

    def test_stepnext_is_reported(self):
        native = {"fps": FPS, "keys": [
            {"time": 0, "value": 0, "outTangentType": "stepnext"},
            {"time": 10, "value": 10}]}
        report = EncodeReport()
        maya_codec.decode(native, report)
        self.assertFalse(report.lossless)


if __name__ == "__main__":
    unittest.main()
