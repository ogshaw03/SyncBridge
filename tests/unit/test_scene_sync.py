"""Scene settings transfer (D-21) and time slider sync (D-22): pure parts."""
import unittest

from syncbridge.core import scene_sync, time_sync


def maya(fps=(24, 1), unit="film", playback=(1, 48), animation=(1, 120), pa=1.0, frame=10.0):
    return {"fps": list(fps), "time_unit": unit, "playback_range": list(playback),
            "animation_range": list(animation), "pixel_aspect": pa, "resolution": [1920, 1080],
            "current_frame": frame}


def ae(rate=24.0, duration=5.0, start=0.0, ws=0.0, wd=5.0, pa=1.0):
    return {"comp": "main", "frameRate": rate, "frameDuration": 1.0 / rate, "duration": duration,
            "displayStartTime": start, "workAreaStart": ws, "workAreaDuration": wd, "pixelAspect": pa,
            "width": 1920, "height": 1080, "time": 0.0}


class MayaToAeTest(unittest.TestCase):
    def test_ranges_follow_the_origin(self):
        plan = scene_sync.maya_to_ae(maya(playback=(11, 34), animation=(1, 120)), ae(duration=4.0, wd=4.0),
                                     origin=1)
        apply = plan["apply"]
        self.assertAlmostEqual(apply["duration"], 5.0)              # frames 1..120 = 120 frames
        self.assertAlmostEqual(apply["displayStartTime"], 1 / 24.0)  # AE shows frame 1 at comp time 0
        self.assertAlmostEqual(apply["workAreaStart"], 10 / 24.0)
        self.assertAlmostEqual(apply["workAreaDuration"], 24 / 24.0)
        self.assertNotIn("frameRate", apply)
        self.assertEqual([c["item"] for c in plan["changes"]], ["animation_range", "playback_range"])
        self.assertEqual(plan["changes"][0]["before"], u"0〜95")
        self.assertEqual(plan["changes"][0]["after"], u"1〜120")
        self.assertEqual(plan["changes"][1]["after"], u"11〜34")

    def test_fps_and_pixel_aspect(self):
        plan = scene_sync.maya_to_ae(maya(fps=(30, 1), unit="ntsc", animation=(1, 150), playback=(1, 150),
                                          pa=2.0), ae(rate=24.0), origin=1)
        apply = plan["apply"]
        self.assertAlmostEqual(apply["frameRate"], 30.0)
        self.assertAlmostEqual(apply["duration"], 5.0)
        self.assertAlmostEqual(apply["displayStartTime"], 1 / 30.0)
        self.assertEqual(apply["pixelAspect"], 2.0)
        self.assertEqual(plan["changes"][0], {"item": "fps", "label": "FPS", "before": "24", "after": "30"})

    def test_same_settings_change_nothing(self):
        plan = scene_sync.maya_to_ae(maya(playback=(1, 120), animation=(1, 120)),
                                     ae(start=1 / 24.0), origin=1)
        self.assertEqual(plan["apply"], {})
        self.assertEqual(scene_sync.describe(plan), u"変更なし")

    def test_only_chosen_items(self):
        plan = scene_sync.maya_to_ae(maya(pa=2.0, fps=(30, 1)), ae(), items=["pixel_aspect"], origin=1)
        self.assertEqual(set(plan["apply"]), {"pixelAspect"})

    def test_animation_start_other_than_origin_is_a_warning(self):
        plan = scene_sync.maya_to_ae(maya(animation=(1001, 1100), playback=(1001, 1100)), ae(), origin=1001)
        self.assertEqual(plan["warnings"], [])
        plan = scene_sync.maya_to_ae(maya(animation=(990, 1100), playback=(1001, 1100)), ae(), origin=1001)
        self.assertEqual(len(plan["warnings"]), 1)
        self.assertAlmostEqual(plan["apply"]["duration"], 100 / 24.0)

    def test_animation_ending_before_the_origin_is_refused(self):
        with self.assertRaises(ValueError):
            scene_sync.maya_to_ae(maya(animation=(1, 50)), ae(), items=["animation_range"], origin=100)

    def test_playback_outside_the_comp_is_clipped(self):
        plan = scene_sync.maya_to_ae(maya(playback=(-10, 300)), ae(duration=5.0, wd=2.0), items=["playback_range"],
                                     origin=1)
        self.assertAlmostEqual(plan["apply"]["workAreaStart"], 0.0)
        self.assertAlmostEqual(plan["apply"]["workAreaDuration"], 5.0 - 0.0)
        self.assertEqual(len(plan["warnings"]), 1)


class AeToMayaTest(unittest.TestCase):
    def test_ranges_and_fps(self):
        plan = scene_sync.ae_to_maya(ae(rate=30.0, duration=4.0, start=1 / 30.0, ws=1.0, wd=2.0, pa=0.9),
                                     maya(), origin=1)
        apply = plan["apply"]
        self.assertEqual(apply["time_unit"], "ntsc")
        self.assertEqual(apply["current_frame"], 10.0)
        self.assertEqual(apply["animation_range"], [1.0, 120.0])
        self.assertEqual(apply["playback_range"], [31.0, 90.0])
        self.assertEqual(apply["pixel_aspect"], 0.9)
        self.assertAlmostEqual(apply["device_aspect"], 1920 / 1080.0 * 0.9)
        self.assertEqual(plan["warnings"], [])

    def test_ntsc_rates(self):
        self.assertEqual(scene_sync.maya_unit_for(23.976023976), "23.976fps")
        self.assertEqual(scene_sync.maya_unit_for([2997, 100]), "29.97fps")      # AE's 29.97 (H-AE-9)
        self.assertEqual(scene_sync.maya_unit_for(24), "film")
        self.assertEqual(scene_sync.maya_unit_for(15), "game")
        with self.assertRaises(ValueError):
            scene_sync.maya_unit_for(18)
        # AE 29.97 and Maya 29.97fps are the same: nothing to change
        plan = scene_sync.ae_to_maya(ae(rate=29.97), maya(fps=(30000, 1001), unit="29.97fps"),
                                     items=["fps"], origin=1)
        self.assertEqual(plan["apply"], {})

    def test_start_frame_other_than_origin_is_a_warning(self):
        plan = scene_sync.ae_to_maya(ae(start=0.0), maya(animation=(1, 100)), items=["animation_range"], origin=1)
        self.assertEqual(plan["apply"]["animation_range"], [1.0, 120.0])
        self.assertEqual(len(plan["warnings"]), 1)

    def test_round_trip(self):
        m = maya(fps=(25, 1), unit="pal", playback=(1011, 1050), animation=(1001, 1100), pa=1.5)
        to_ae = scene_sync.maya_to_ae(m, ae(), origin=1001)
        a = dict(ae(), **{k: v for k, v in to_ae["apply"].items()})
        back = scene_sync.ae_to_maya(a, m, origin=1001)
        self.assertEqual(back["apply"], {})


class ConfirmAndReadbackTest(unittest.TestCase):
    def test_confirm_text_lists_the_changes(self):
        plan = scene_sync.ae_to_maya(ae(rate=30.0, duration=4.0, start=1 / 30.0, ws=0, wd=4.0), maya(), origin=1)
        text = scene_sync.confirm_text(plan, u"After Effects のコンプ「main」")
        self.assertIn(u"FPS: 24 → 30", text)
        self.assertIn(u"キーはフレーム番号のまま", text)
        self.assertIn(u"取り消し（Ctrl+Z）を 1 回", text)

    def test_check_after(self):
        plan = scene_sync.maya_to_ae(maya(playback=(11, 34)), ae(), origin=1)
        good = dict(ae(), **plan["apply"])
        self.assertEqual(scene_sync.check_after(plan, good), [])
        bad = dict(good, workAreaStart=0.0)
        self.assertEqual([p["key"] for p in scene_sync.check_after(plan, bad)], ["workAreaStart"])
        plan = scene_sync.ae_to_maya(ae(rate=30.0), maya(), origin=1)
        after = maya(fps=(30, 1), unit="ntsc", animation=plan["apply"]["animation_range"],
                     playback=plan["apply"]["playback_range"])
        self.assertEqual(scene_sync.check_after(plan, after), [])

    def test_items_are_checked(self):
        with self.assertRaises(ValueError):
            scene_sync.maya_to_ae(maya(), ae(), items=["resolution"])
        with self.assertRaises(ValueError):
            scene_sync.maya_to_ae(maya(), ae(), items=[])


class TimeSyncTest(unittest.TestCase):
    def test_frames_and_times(self):
        self.assertAlmostEqual(time_sync.maya_frame_to_time(25, [24, 1], 1), 1.0)
        self.assertEqual(time_sync.time_to_maya_frame(1.0, [24, 1], 1), 25.0)
        self.assertEqual(time_sync.time_to_maya_frame(1 / 30.0 * 7, [30, 1], 1001), 1008.0)
        self.assertAlmostEqual(time_sync.time_to_maya_frame(0.5 / 24, [24, 1], 1), 1.5)

    def test_throttle(self):
        now = [0.0]
        th = time_sync.Throttle(0.1, clock=lambda: now[0])
        self.assertTrue(th.offer(1))
        now[0] = 0.05
        self.assertFalse(th.offer(2))
        self.assertFalse(th.offer(3))
        self.assertAlmostEqual(th.wait(), 0.05)
        self.assertIsNone(th.due())
        now[0] = 0.1
        self.assertEqual(th.due(), 3)
        self.assertIsNone(th.due())
        now[0] = 0.3
        self.assertTrue(th.offer(4))

    def test_latency_stats(self):
        stats = time_sync.LatencyStats(keep=3)
        self.assertEqual(stats.summary(), u"")
        for ms in (10, 20, 30, 40):
            stats.add("recv", ms)
        stats.add("apply", 5)
        self.assertEqual(stats.summary(), u"受け取るまで 平均 30 ms（最大 40、3 回）、Maya で時間を設定 平均 5 ms（最大 5、1 回）")
        stats.clear()
        self.assertEqual(stats.summary(), u"")

    def test_echo_guard(self):
        guard = time_sync.EchoGuard()
        guard.applied(25.0)
        self.assertFalse(guard.is_echo(26.0))
        self.assertTrue(guard.is_echo(25.0))
        self.assertFalse(guard.is_echo(25.0))      # only once


if __name__ == "__main__":
    unittest.main()
