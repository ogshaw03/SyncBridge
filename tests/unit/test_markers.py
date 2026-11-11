"""AE key timings as Maya markers (D-18)."""
import unittest

from syncbridge.core import ae_codec, jobs, markers, testcurves


def ae_data(keys=None, start=0.0, source=None, comp_fps=24.0):
    keys = keys if keys is not None else ae_codec.encode(testcurves.slowmo_linear())
    layer = {"name": "render", "startTime": start, "stretch": 100}
    if source is not None:
        layer["source"] = source
    return {"comp": {"name": "main", "frameRate": comp_fps, "frameDuration": 1 / comp_fps, "duration": 4.0},
            "layer": layer, "keys": keys}


class MarkerTest(unittest.TestCase):
    def test_keys_become_maya_frames_with_the_origin(self):
        # slowmo_linear keys at comp 0, 1, 3, 4 s with values 0, 1, 2, 3 s.
        result = markers.from_ae_export(ae_data(), [24, 1], {"origin": 1001})
        frames = [m["frame"] for m in result["markers"]]
        self.assertEqual(frames, [1001.0, 1025.0, 1073.0, 1097.0])
        self.assertEqual([m["source_frame"] for m in result["markers"]], [0.0, 24.0, 48.0, 72.0])
        self.assertEqual(result["markers"][2]["label"], u"AE キー 3/4  素材 48f")
        self.assertEqual((result["comp"], result["layer"], result["origin"]), ("main", "render", 1001.0))

    def test_same_frames_as_an_ae_to_maya_transfer(self):
        data = ae_data(start=0.5)
        opts = {"origin": 1}
        result = markers.from_ae_export(data, [24, 1], opts)
        ctx = jobs.mapping_context(jobs.TransferOptions.from_json(opts), [24, 1], layer_start=0.5)
        self.assertEqual([m["frame"] for m in result["markers"]],
                         [ctx.comp_time_to_maya_frame(k["time"]) for k in data["keys"]])
        self.assertEqual(result["markers"][0]["frame"], 1 - 12)       # layer starts 0.5 s later in the comp

    def test_source_frame_rate_and_subframes(self):
        data = ae_data(source={"name": "seq", "duration": 10.0, "frameRate": 30.0})
        result = markers.from_ae_export(data, [24, 1], {"origin": 0})
        self.assertEqual(result["markers"][1]["source_frame"], 30.0)
        keys = ae_codec.encode(testcurves.slowmo_linear())
        keys[1]["value"] = 1.01
        result = markers.from_ae_export(ae_data(keys), [24, 1], {"origin": 0})
        self.assertIn(u"素材 24.24f", result["markers"][1]["label"])

    def test_keys_are_sorted_and_numbered(self):
        keys = list(reversed(ae_codec.encode(testcurves.slowmo_linear())))
        result = markers.from_ae_export(ae_data(keys), [24, 1], {"origin": 0})
        self.assertEqual([m["index"] for m in result["markers"]], [1, 2, 3, 4])
        self.assertEqual([m["comp_time"] for m in result["markers"]], [0.0, 1.0, 3.0, 4.0])

    def test_no_keys(self):
        with self.assertRaises(ValueError) as ctx:
            markers.from_ae_export(ae_data(keys=[]), [24, 1], {"origin": 0})
        self.assertIn(u"キーがありません", str(ctx.exception))
        with self.assertRaises(ValueError):
            markers.from_ae_export(ae_data(), [24, 1], {"origin": 0, "unknown": 1})

    def test_marker_at(self):
        result = markers.from_ae_export(ae_data(), [24, 1], {"origin": 1})
        ms = result["markers"]
        self.assertEqual(markers.marker_at(ms, 25.0)["index"], 2)
        self.assertEqual(markers.marker_at(ms, 25.4)["index"], 2)
        self.assertIsNone(markers.marker_at(ms, 25.6))
        self.assertIsNone(markers.marker_at([], 1.0))


class MayaMarkersTest(unittest.TestCase):
    """D-55: markers made in Maya carry their AE comp time, for a later sync with AE."""

    def test_frames_to_comp_times_and_back(self):
        result = markers.from_maya_frames([1049, 1001, 1025], [24, 1], 1001)
        self.assertEqual(result["source"], "maya")
        self.assertEqual([m["frame"] for m in result["markers"]], [1001.0, 1025.0, 1049.0])
        self.assertEqual([m["comp_time"] for m in result["markers"]], [0.0, 1.0, 2.0])
        self.assertEqual(result["markers"][1]["label"], u"マーカー 2/3")
        times = [m["comp_time"] for m in result["markers"]]
        self.assertEqual(markers.maya_frames_from_comp_times(times, [24, 1], 1001), [1001.0, 1025.0, 1049.0])

    def test_ntsc_rate_comes_back_on_whole_frames(self):
        result = markers.from_maya_frames([10, 37], [24000, 1001], 0)
        times = [m["comp_time"] for m in result["markers"]]
        self.assertEqual(markers.maya_frames_from_comp_times(times, [24000, 1001], 0), [10.0, 37.0])

    def test_none(self):
        self.assertEqual(markers.from_maya_frames([], [24, 1], 0)["markers"], [])


if __name__ == "__main__":
    unittest.main()
