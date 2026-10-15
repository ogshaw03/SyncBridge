"""Regression tests against values Maya itself evaluated (no Maya needed).

Fixture: tests/fixtures/maya2024_probe_run3.json, from Maya probe run 3
(Maya 2024, film / 24 fps, 2026-10-16). `raw` is what Maya reported for each
animCurveTT (keyframe / keyTangent queries), `samples` are `keyframe -eval`
results including 12 frames before and after the keys: ground truth for how
Maya evaluates the curve, extrapolation included.
"""
import json
import os
import sys
import types
import unittest

from syncbridge.core import maya_codec
from syncbridge.core.ae_codec import EncodeReport
from syncbridge.core.timebase import FrameRate
from syncbridge.core.validation import compare_samples

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURE = os.path.join(REPO, "tests", "fixtures", "maya2024_probe_run3.json")
MAYA_SCRIPTS = os.path.join(REPO, "maya_plugin", "scripts")
FPS = FrameRate(24)
TOLERANCE_FRAMES = 0.01


def _maya_modules():
    return [k for k in sys.modules if k == "maya" or k.startswith(("maya.", "syncbridge_maya"))]


class MayaRealDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE, encoding="utf-8") as f:
            cls.data = json.load(f)
        # raw_to_native is pure; a stub maya package is enough to import the adapter.
        cls.saved = {k: sys.modules.pop(k) for k in _maya_modules()}
        maya = types.ModuleType("maya")
        maya.cmds = types.ModuleType("maya.cmds")
        maya.mel = types.ModuleType("maya.mel")
        sys.modules.update({"maya": maya, "maya.cmds": maya.cmds, "maya.mel": maya.mel})
        sys.path.insert(0, MAYA_SCRIPTS)
        from syncbridge_maya import anim_curve
        cls.anim_curve = anim_curve

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(MAYA_SCRIPTS)
        for k in _maya_modules():
            del sys.modules[k]
        sys.modules.update(cls.saved)

    def decode(self, raw, weight_scale=None):
        scale = weight_scale or self.anim_curve.DEFAULT_WEIGHT_SCALE
        return maya_codec.decode(self.anim_curve.raw_to_native(raw, FPS, scale))

    def compare(self, curve, frames, values):
        spf = FPS.frame_duration
        return compare_samples([f * spf for f in frames], [v * spf for v in values],
                               curve.evaluate, FPS, TOLERANCE_FRAMES)

    def overruns(self, raw):
        report = EncodeReport()
        maya_codec.decode(self.anim_curve.raw_to_native(raw, FPS), report)
        return any("H-MY-13" in w for w in report.warnings)

    def test_every_written_curve_decodes_to_maya_evaluation(self):
        # Covers H-MY-4/5/7 and extrapolation, for curves written with any weight scale:
        # reading uses the confirmed scale, so it must reproduce what Maya evaluates.
        # Exception: a single handle longer than its segment (H-MY-13, unresolved).
        checked = 0
        for w in self.data["write_roundtrip"]:
            if self.overruns(w["raw"]):
                continue
            report = self.compare(self.decode(w["raw"]), w["samples"]["frames"], w["samples"]["values"])
            self.assertTrue(report.passed, "%s / %s: %s" % (w["curve"], w["weight_scale"], report.summary()))
            checked += 1
        self.assertEqual(checked, 18)

    def test_overlong_handles_are_reported(self):
        # H-MY-13: the two run-3 curves whose handle exceeds the segment do not match Maya;
        # decoding must at least warn about them.
        flagged = [(w["curve"], w["weight_scale"]) for w in self.data["write_roundtrip"] if self.overruns(w["raw"])]
        self.assertEqual(sorted(flagged), [("asymmetric_ease", "w/3 (frames)"), ("linear_then_ease", "w/3 (frames)")])

    def test_only_confirmed_weight_scale_matches(self):
        w = next(w for w in self.data["write_roundtrip"]
                 if w["curve"] == "asymmetric_ease" and w["weight_scale"] == "w (frames)")
        wrong = self.compare(self.decode(w["raw"], "w/3 (frames)"), w["samples"]["frames"], w["samples"]["values"])
        self.assertFalse(wrong.passed)

    def test_scene_warp_extrapolates_along_outer_tangents(self):
        # H-MY-11 corrected: first key's in tangent / last key's out tangent (both 0 deg here),
        # although the inner tangents are 45 deg and both infinities are linear.
        sw = self.data["scene_warp"]
        self.assertEqual((sw["raw"]["preInfinity"], sw["raw"]["postInfinity"]), ("linear", "linear"))
        ext = sw["extrapolation"]
        report = self.compare(self.decode(sw["raw"]), [e["frame"] for e in ext], [e["maya"] for e in ext])
        self.assertTrue(report.passed, report.summary())

    def test_set_infinity_fix_writes_linear_extrapolation(self):
        # Run 4: with set_infinity (enum attribute) Maya kept linear infinity and the
        # outer tangents, and extrapolated with slope 0.5 for 12 frames on both sides.
        w = self.data["run4_linear_infinity"]
        self.assertEqual((w["raw"]["preInfinity"], w["raw"]["postInfinity"]), ("linear", "linear"))
        frames, values = w["samples"]["frames"], w["samples"]["values"]
        self.assertLess(frames[0], w["raw"]["times"][0])
        self.assertGreater(frames[-1], w["raw"]["times"][-1])
        report = self.compare(self.decode(w["raw"]), frames, values)
        self.assertTrue(report.passed, report.summary())
        # Round trip: what SyncBridge sends decodes to the same curve Maya evaluates.
        sent = self.compare(maya_codec.decode(w["native_sent"]), frames, values)
        self.assertTrue(sent.passed, sent.summary())

    def test_set_infinity_did_not_reach_the_curve(self):
        # H-MY-12: run 3 wrote linear infinity with setInfinity; Maya kept Constant.
        w = next(w for w in self.data["write_roundtrip"] if w["curve"] == "linear_infinity")
        self.assertEqual(w["native_sent"]["preInfinity"], "linear")
        self.assertEqual(w["raw"]["preInfinity"], "constant")


if __name__ == "__main__":
    unittest.main()
