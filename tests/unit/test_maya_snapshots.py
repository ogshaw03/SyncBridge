"""syncbridge_maya.snapshots (save / list / restore / retime) with a fake Maya."""
import os
import shutil
import sys
import tempfile
import time
import types
import unittest

from syncbridge.core import envelope, maya_codec, testcurves, warp_edit
from syncbridge.core.timebase import FrameRate

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAYA_SCRIPTS = os.path.join(REPO, "maya_plugin", "scripts")


def _maya_modules():
    return [k for k in sys.modules if k == "maya" or k.startswith(("maya.", "syncbridge_maya"))]


def maya_native(curve=None, fps=(24, 1)):
    curve = (curve or testcurves.speed_ramp_bezier()).affine(in_offset=1 / 24.0, out_offset=1 / 24.0)
    return maya_codec.encode(curve, list(fps))


class SnapshotsTest(unittest.TestCase):
    def setUp(self):
        self.saved = {k: sys.modules.pop(k) for k in _maya_modules()}
        self.tmp = tempfile.mkdtemp()
        cmds = types.ModuleType("maya.cmds")
        cmds.internalVar = lambda userAppDir=False: self.tmp + "/"
        cmds.file = lambda q=False, sn=False: "C:/shots/shot010.mb"
        maya = types.ModuleType("maya")
        maya.cmds, maya.mel = cmds, types.ModuleType("maya.mel")
        sys.modules.update({"maya": maya, "maya.cmds": cmds, "maya.mel": maya.mel})
        sys.path.insert(0, MAYA_SCRIPTS)
        from syncbridge_maya import anim_curve, exchange, snapshots
        self.snapshots, self.exchange = snapshots, exchange
        self.native = maya_native()
        exchange.build_export = lambda allow_missing=False, **kw: envelope.make(
            "maya.timewarp.export", {"native": self.native, "scene": {"fps": [24, 1]}}, "maya",
            {"name": "maya", "scene": "C:/shots/shot010.mb"})
        self.applied = []
        exchange.apply_envelope = lambda env, confirm=True, origin="": (
            self.applied.append((env, confirm, origin)) or {"status": "applied"})
        anim_curve.scene_fps = lambda: FrameRate(24)

    def tearDown(self):
        sys.path.remove(MAYA_SCRIPTS)
        for k in _maya_modules():
            del sys.modules[k]
        sys.modules.update(self.saved)
        shutil.rmtree(self.tmp)

    def test_save_names(self):
        a = self.snapshots.save(u"シーン A: take/1")
        self.assertEqual(os.path.basename(a), u"シーン_A_take_1.json")
        b = self.snapshots.save(u"シーン A: take/1")
        self.assertEqual(os.path.basename(b), u"シーン_A_take_1_2.json")
        c = self.snapshots.save("")
        self.assertTrue(os.path.basename(c).startswith("shot010_"))
        data = envelope.load(a, "maya.timewarp.export")["data"]
        self.assertEqual(data["native"], self.native)
        self.assertEqual(data["snapshot_name"], u"シーン_A_take_1")

    def test_save_without_warp(self):
        self.native = None
        with self.assertRaises(RuntimeError):
            self.snapshots.save("x")

    def test_entries_include_backups_newest_first(self):
        first = self.snapshots.save("first")
        time.sleep(0.05)
        backup = os.path.join(self.exchange.backup_dir(), "timewarp_20261016_120000.json")
        envelope.save(backup, self.exchange.build_export())
        time.sleep(0.05)
        newest = self.snapshots.save("newest")
        with open(os.path.join(self.snapshots.snapshot_dir(), "broken.json"), "w") as f:
            f.write("{not json")
        items = self.snapshots.entries()
        self.assertEqual([i["path"] for i in items], [newest, backup, first])
        self.assertEqual([i["kind"] for i in items], ["snapshot", "backup", "snapshot"])
        self.assertEqual(items[0]["frames"], warp_edit.key_range(self.native))
        self.assertEqual(items[0]["scene"], "shot010.mb")

    def test_restore_converts_fps_and_retimes(self):
        self.native = maya_native(fps=(30, 1))            # saved in a 30 fps scene
        path = self.snapshots.save("at30")
        self.native = maya_native()
        self.snapshots.restore(path)
        env, confirm, origin = self.applied[-1]
        self.assertTrue(confirm)
        self.assertEqual(env["kind"], "maya.timewarp.apply")
        self.assertEqual(env["data"]["native"]["fps"], [24, 1])
        self.assertIn(u"「at30」", origin)
        self.snapshots.restore(path, new_range=(10.0, 100.0))
        env, _, origin = self.applied[-1]
        self.assertEqual(warp_edit.key_range(env["data"]["native"]), (10.0, 100.0))
        self.assertIn(u"10〜100", origin)

    def test_retime_current(self):
        self.snapshots.retime_current(1.0, 200.0)
        env, confirm, origin = self.applied[-1]
        self.assertEqual(warp_edit.key_range(env["data"]["native"]), (1.0, 200.0))
        self.assertEqual(warp_edit.value_range(env["data"]["native"]), warp_edit.value_range(self.native))
        self.assertIn(u"範囲の変更", origin)


if __name__ == "__main__":
    unittest.main()
