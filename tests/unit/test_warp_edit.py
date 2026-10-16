import unittest

from syncbridge.core import maya_codec, testcurves, warp_edit

FPS = [24, 1]


def native_of(curve, origin=1.0):
    o = origin / 24.0
    return maya_codec.encode(curve.affine(in_offset=o, out_offset=o), FPS)


class RetimeTest(unittest.TestCase):
    def assert_shape(self, before, after, old, new):
        """after(new frame) == before(corresponding old frame) everywhere in the range."""
        b, a = maya_codec.decode(before), maya_codec.decode(after)
        for i in range(201):
            f_new = new[0] + (new[1] - new[0]) * i / 200.0
            f_old = old[0] + (old[1] - old[0]) * i / 200.0
            self.assertAlmostEqual(a.evaluate(f_new / 24.0) * 24.0, b.evaluate(f_old / 24.0) * 24.0, places=6)

    def test_stretch_keeps_values_and_shape(self):
        for name, make in testcurves.CURVES.items():
            before = native_of(make())
            old = warp_edit.key_range(before)
            new = (1.0, 1.0 + (old[1] - old[0]) * 2)          # twice as long
            after = warp_edit.retime(before, *new)
            self.assertEqual(warp_edit.key_range(after), new, name)
            self.assertEqual(warp_edit.value_range(after), warp_edit.value_range(before), name)
            self.assert_shape(before, after, old, new)

    def test_shrink_and_move(self):
        before = native_of(testcurves.asymmetric_ease())          # weighted handles
        old = warp_edit.key_range(before)
        after = warp_edit.retime(before, 101.0, 101.0 + (old[1] - old[0]) * 0.5)
        self.assert_shape(before, after, old, warp_edit.key_range(after))

    def test_hold_stays_a_hold(self):
        after = warp_edit.retime(native_of(testcurves.freeze_hold()), 0.0, 48.0)
        self.assertIn("step", [k["outTangentType"] for k in after["keys"]])

    def test_explicit_old_range(self):
        before = native_of(testcurves.slowmo_linear())           # keys at 1..97
        after = warp_edit.retime(before, 11.0, 107.0, old_start=1.0, old_end=97.0)
        self.assertEqual(warp_edit.key_range(after), (11.0, 107.0))

    def test_infinity_kept(self):
        after = warp_edit.retime(native_of(testcurves.linear_infinity()), 1.0, 100.0)
        self.assertEqual((after["preInfinity"], after["postInfinity"]), ("linear", "linear"))

    def test_bad_ranges(self):
        before = native_of(testcurves.slowmo_linear())
        with self.assertRaises(ValueError):
            warp_edit.retime(before, 10.0, 10.0)
        with self.assertRaises(ValueError):
            warp_edit.retime(before, 20.0, 10.0)

    def test_to_scene_fps(self):
        before = native_of(testcurves.speed_ramp_bezier())
        at30 = warp_edit.to_scene_fps(before, [30, 1])
        self.assertEqual(at30["fps"], [30, 1])
        b, a = maya_codec.decode(before), maya_codec.decode(at30)
        for t in (0.1, 0.5, 1.3, 2.9):
            self.assertAlmostEqual(a.evaluate(t), b.evaluate(t), places=6)    # same in seconds
        self.assertIs(warp_edit.to_scene_fps(before, [24, 1]), before)


if __name__ == "__main__":
    unittest.main()
