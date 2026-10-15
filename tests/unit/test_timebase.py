import unittest
from fractions import Fraction

from syncbridge.core.timebase import FrameRate, snap_rate


class FrameRateTest(unittest.TestCase):
    def test_ntsc_float_snaps_to_exact_rational(self):
        # AE reports comp.frameRate as a float such as 23.976023976...
        self.assertEqual(FrameRate(24000 / 1001).fraction, Fraction(24000, 1001))
        self.assertEqual(FrameRate(23.976).fraction, Fraction(24000, 1001))
        self.assertEqual(FrameRate(29.97).fraction, Fraction(30000, 1001))
        self.assertEqual(snap_rate(59.94), Fraction(60000, 1001))

    def test_parse_forms(self):
        self.assertEqual(FrameRate("24000/1001").fraction, Fraction(24000, 1001))
        self.assertEqual(FrameRate([25, 1]).fraction, Fraction(25))
        self.assertEqual(FrameRate(24), FrameRate("24"))
        with self.assertRaises(ValueError):
            FrameRate(0)

    def test_maya_units(self):
        self.assertEqual(FrameRate.from_maya_unit("film").fps, 24.0)
        self.assertEqual(FrameRate.from_maya_unit("pal").fps, 25.0)
        self.assertEqual(FrameRate.from_maya_unit("ntsc").fps, 30.0)
        self.assertEqual(FrameRate.from_maya_unit("23.976fps").fraction, Fraction(24000, 1001))
        self.assertEqual(FrameRate.from_maya_unit("12fps").fps, 12.0)
        with self.assertRaises(ValueError):
            FrameRate.from_maya_unit("bogus")

    def test_frames_seconds_roundtrip(self):
        r = FrameRate(Fraction(24000, 1001))
        self.assertAlmostEqual(r.frames_to_seconds(24000), 1001.0, places=9)
        self.assertAlmostEqual(r.seconds_to_frames(r.frames_to_seconds(1234.5)), 1234.5, places=9)

    def test_json_roundtrip(self):
        r = FrameRate(Fraction(30000, 1001))
        self.assertEqual(FrameRate.from_json(r.to_json()), r)


if __name__ == "__main__":
    unittest.main()
