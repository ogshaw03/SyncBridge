"""Regression tests against values After Effects itself evaluated (no AE needed).

Fixture: tests/fixtures/ae26.5_probe_run2.json, a subset of AE probe run 2
(AE 26.5, 2026-10-16). `times`/`values` are AE's valueAtTime results, i.e.
ground truth for how AE interprets the keys.
"""
import json
import os
import unittest

from syncbridge import cli
from syncbridge.core import ae_codec
from syncbridge.core.validation import compare_samples

FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "fixtures", "ae26.5_probe_run2.json")
TOLERANCE_FRAMES = 0.01


class AERealDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE, encoding="utf-8") as f:
            data = json.load(f)["data"]
        cls.fps = data["comp_fps"]
        cls.results = {r["name"]: r for r in data["results"]}

    def check(self, name, keys_field):
        r = self.results[name]
        curve = ae_codec.decode(r[keys_field])
        report = compare_samples(r["times"], r["values"], curve.evaluate, self.fps, TOLERANCE_FRAMES)
        self.assertTrue(report.passed, "%s (%s): %s" % (name, keys_field, report.summary()))

    def test_codec_matches_ae_for_every_vector(self):
        for name in self.results:
            self.check(name, "sentKeys")
            self.check(name, "readKeys")

    def test_mixed_linear_bezier_uses_one_sixth_chord(self):
        # H-AE-6: with the old 1/3 rule this vector was off by 2.85 frames.
        self.check("ae_mixed_linear_bezier", "sentKeys")
        r = self.results["ae_mixed_linear_bezier"]
        saved = ae_codec.LINEAR_SIDE_FRACTION
        try:
            ae_codec.LINEAR_SIDE_FRACTION = 1.0 / 3.0
            curve = ae_codec.decode(r["sentKeys"])
            report = compare_samples(r["times"], r["values"], curve.evaluate, self.fps, TOLERANCE_FRAMES)
            self.assertFalse(report.passed)
        finally:
            ae_codec.LINEAR_SIDE_FRACTION = saved

    def test_ae_kept_keys_as_sent(self):
        # H-AE-5 (sub-frame times kept) and H-AE-11 (types kept after the applyKeys fix).
        for name, r in self.results.items():
            if name == "ae_mixed_linear_bezier":
                continue  # raw vector: its LINEAR-side ease is rewritten by AE (H-AE-12)
            self.assertEqual(cli._key_changes(r["sentKeys"], r["readKeys"], self.fps), "none", name)

    def test_linear_side_ease_is_rewritten_to_chord(self):
        # H-AE-12: AE stores (chord slope, 16.667 %) on LINEAR sides.
        key = self.results["ae_mixed_linear_bezier"]["readKeys"][0]
        self.assertEqual(key["outInterp"], "LINEAR")
        self.assertAlmostEqual(key["outEase"]["speed"], 1.0, places=6)
        self.assertAlmostEqual(key["outEase"]["influence"], 100.0 / 6.0, places=4)


if __name__ == "__main__":
    unittest.main()
