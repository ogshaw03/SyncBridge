"""Maya adapter logic tested against a fake maya.cmds (reproduces probe findings)."""
import os
import sys
import types
import unittest

from syncbridge.core.timebase import FrameRate

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAYA_SCRIPTS = os.path.join(REPO, "maya_plugin", "scripts")


class FakeCmds(types.ModuleType):
    """Answers the queries read_raw() makes, like Maya 2024 did in the first probe."""

    def __init__(self):
        super().__init__("maya.cmds")
        self.keys = {"times": [1.0, 25.0], "values": [1.0, 13.0]}
        self.infinity_query = None              # Maya 2024: setInfinity -q returned None
        self.infinity_attr = {"pre": "Constant", "post": "Linear"}
        self.tangent_override = {}

    def keyframe(self, curve, q=False, keyframeCount=False, timeChange=False, valueChange=False, **kw):
        if keyframeCount:
            return len(self.keys["times"])
        if timeChange:
            return list(self.keys["times"])
        if valueChange:
            return list(self.keys["values"])
        raise AssertionError("unexpected keyframe query")

    def keyTangent(self, curve, q=False, **flags):
        (flag,) = flags
        if flag in self.tangent_override:
            return self.tangent_override[flag]
        n = len(self.keys["times"])
        return {
            "inTangentType": ["spline"] * n, "outTangentType": ["spline"] * n,
            "inAngle": [26.565] * n, "outAngle": [26.565] * n,
            "inWeight": [1.0] * n, "outWeight": [1.0] * n,
            "weightedTangents": [False],
        }[flag]

    def setInfinity(self, curve, q=False, **flags):
        return self.infinity_query

    def getAttr(self, plug, asString=False):
        node, attr = plug.split(".")
        return self.infinity_attr[attr.replace("Infinity", "")]


class MayaAdapterTest(unittest.TestCase):
    def setUp(self):
        self.saved = {k: v for k, v in sys.modules.items() if k == "maya" or k.startswith(("maya.", "syncbridge_maya"))}
        for k in self.saved:
            del sys.modules[k]
        self.cmds = FakeCmds()
        maya = types.ModuleType("maya")
        maya.cmds = self.cmds
        maya.mel = types.ModuleType("maya.mel")
        sys.modules.update({"maya": maya, "maya.cmds": self.cmds, "maya.mel": maya.mel})
        sys.path.insert(0, MAYA_SCRIPTS)
        from syncbridge_maya import anim_curve
        self.anim_curve = anim_curve

    def tearDown(self):
        sys.path.remove(MAYA_SCRIPTS)
        for k in [k for k in sys.modules if k == "maya" or k.startswith(("maya.", "syncbridge_maya"))]:
            del sys.modules[k]
        sys.modules.update(self.saved)

    def test_infinity_falls_back_to_node_attribute(self):
        # Probe 2026-10-16 (Maya 2024): setInfinity -q returned None -> TypeError.
        raw = self.anim_curve.read_raw("timewarp")
        self.assertEqual(raw["preInfinity"], "constant")
        self.assertEqual(raw["postInfinity"], "linear")

    def test_infinity_query_result_is_used_when_available(self):
        self.cmds.infinity_query = ["Cycle"]
        self.assertEqual(self.anim_curve.query_infinity("timewarp", "pre"), "cycle")

    def test_unsupported_infinity_is_warned(self):
        self.cmds.infinity_attr["post"] = "Cycle with Offset"
        native = self.anim_curve.raw_to_native(self.anim_curve.read_raw("timewarp"), FrameRate(24))
        self.assertEqual(native["postInfinity"], "constant")
        self.assertTrue(any("postInfinity" in w for w in native["warnings"]))

    def test_missing_query_result_raises_clear_error(self):
        self.cmds.tangent_override["inAngle"] = None
        with self.assertRaises(RuntimeError) as ctx:
            self.anim_curve.read_raw("timewarp")
        self.assertIn("inAngle", str(ctx.exception))

    def test_slope_from_angle(self):
        native = self.anim_curve.raw_to_native(self.anim_curve.read_raw("timewarp"), FrameRate(24))
        # H-MY-4: tan(26.565 deg) = 0.5
        self.assertAlmostEqual(native["keys"][0]["outSlope"], 0.5, places=4)


if __name__ == "__main__":
    unittest.main()
