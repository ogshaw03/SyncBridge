"""DCC-free integration tests: CLI file pipeline and the ExtendScript JSON helper."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from syncbridge import cli
from syncbridge.core import envelope, maya_codec, testcurves

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JSON_JSXINC = os.path.join(REPO, "after_effects", "jsx", "syncbridge_json.jsxinc")


class CliPipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def path(self, name):
        return os.path.join(self.tmp, name)

    def test_selftest(self):
        self.assertEqual(cli.main(["selftest"]), 0)

    def test_maya_to_ae_to_maya_files(self):
        curve = testcurves.speed_ramp_bezier().affine(in_offset=1001 / 24.0, out_offset=1001 / 24.0)
        native = maya_codec.encode(curve, [24, 1])
        envelope.save(self.path("maya.json"), envelope.make("maya.timewarp.export", {
            "native": native, "samples": None, "scene": {"fps": [24, 1]}}))
        self.assertEqual(cli.main(["maya2ae", self.path("maya.json"), "-o", self.path("ae_apply.json"),
                                   "--origin", "1001", "--mode", "precision"]), 0)
        ae_apply = envelope.load(self.path("ae_apply.json"), "ae.timeremap.apply")["data"]
        self.assertGreater(len(ae_apply["keys"]), 2)

        # Simulate AE: export of the applied layer, evaluated exactly.
        from syncbridge.core import ae_codec
        applied = ae_codec.decode(ae_apply["keys"])
        times = [i / 96.0 for i in range(0, 289)]
        envelope.save(self.path("ae_export.json"), envelope.make("ae.timeremap.export", {
            "comp": {"frameRate": 24.0}, "layer": {"startTime": 0.0},
            "keys": ae_apply["keys"],
            "samples": {"times": times, "values": [applied.evaluate(t) for t in times]}}))
        self.assertEqual(cli.main(["readback", self.path("ae_apply.json"), self.path("ae_export.json")]), 0)
        self.assertEqual(cli.main(["ae2maya", self.path("ae_export.json"), "-o", self.path("maya_apply.json"),
                                   "--maya-fps", "24", "--origin", "1001"]), 0)
        back = maya_codec.decode(envelope.load(self.path("maya_apply.json"))["data"]["native"])
        self.assertAlmostEqual(back.evaluate(1001 / 24.0 + 1.0), curve.evaluate(1001 / 24.0 + 1.0), delta=0.1 / 24)

    def test_readback_detects_mismatch(self):
        from syncbridge.core import ae_codec
        keys = ae_codec.encode(testcurves.slowmo_linear())
        envelope.save(self.path("apply.json"), envelope.make("ae.timeremap.apply", {
            "mode": "editable", "comp_fps": [24, 1], "keys": keys}))
        envelope.save(self.path("after.json"), envelope.make("ae.timeremap.export", {
            "comp": {}, "layer": {}, "keys": keys,
            "samples": {"times": [0.0, 2.0], "values": [0.0, 1.6]}}))   # 1.5 expected
        self.assertEqual(cli.main(["readback", self.path("apply.json"), self.path("after.json")]), 2)

    def test_probe_vectors(self):
        self.assertEqual(cli.main(["probe-vectors", "-o", self.path("v.json")]), 0)
        data = envelope.load(self.path("v.json"), "ae.probe.vectors")["data"]
        self.assertEqual(len(data["vectors"]), len(testcurves.PROBE_CURVES))

    def test_envelope_rejects_foreign_files(self):
        with self.assertRaises(ValueError):
            envelope.check({"schema": "other"})
        with self.assertRaises(ValueError):
            envelope.check(envelope.make("ae.timeremap.apply", {}), "maya.timewarp.apply")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ExtendScriptJsonTest(unittest.TestCase):
    """Runs the ES3 JSON helper in Node to check it agrees with Python's json."""

    def run_js(self, body):
        with open(JSON_JSXINC, encoding="utf-8") as f:
            src = f.read()
        out = subprocess.run(["node", "-e", src + "\n" + body], capture_output=True, encoding="utf-8", timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout

    def test_roundtrip_with_python(self):
        payload = {"a": [1, 2.5, -3e-7, None, True], "s": "日本語 \"q\" \\ \n\t", "o": {"k": []}}
        text = json.dumps(payload, ensure_ascii=False)
        out = self.run_js("var o = SBJSON.parse(%s); process.stdout.write(SBJSON.stringify(o, '  '));"
                          % json.dumps(text))
        self.assertEqual(json.loads(out), payload)

    def test_all_jsx_files_parse(self):
        """Syntax-only check of every JSX file (the `#include` preprocessor lines are removed).

        Node parses a superset of ES3, so this catches syntax errors but not
        ES5+ features that ExtendScript lacks; see CLAUDE.md for the ES3 rules.
        """
        jsx_dir = os.path.join(REPO, "after_effects", "jsx")
        for name in sorted(os.listdir(jsx_dir)):
            if not name.endswith((".jsx", ".jsxinc")):
                continue
            with open(os.path.join(jsx_dir, name), encoding="utf-8") as f:
                src = "\n".join("" if line.startswith("#include") else line for line in f.read().splitlines())
            for ch in src:
                self.assertLess(ord(ch), 128, "%s contains non-ASCII character %r" % (name, ch))
            body = "new Function(%s); process.stdout.write('ok');" % json.dumps(src)
            out = subprocess.run(["node", "-e", body], capture_output=True, encoding="utf-8", timeout=60)
            self.assertEqual(out.returncode, 0, "%s: %s" % (name, out.stderr))

    def test_rejects_non_json(self):
        out = self.run_js("try { SBJSON.parse('alert(1)'); process.stdout.write('accepted'); }"
                          " catch (e) { process.stdout.write('rejected'); }")
        self.assertEqual(out, "rejected")


if __name__ == "__main__":
    unittest.main()
