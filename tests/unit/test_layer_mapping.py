"""Virtual Layer Mapping records (Pixel Mapping Phase 2)."""
import unittest

from syncbridge.core import layer_mapping as lm

AE = {"comp_id": 12, "comp": "c010", "layer_id": 345, "layer": "BG", "source": "bg.png",
      "source_width": 6000, "source_height": 4000}
MAYA = {"camera_uuid": "CAM-UUID", "camera": "|BG_CAM|BG_CAMShape", "bg_uuid": "BG-UUID", "bg": "|bgPlane"}


class LayerMappingTest(unittest.TestCase):
    def test_new_and_find(self):
        m = lm.new_mapping(AE, MAYA)
        self.assertTrue(m["id"].startswith("vl-"))
        self.assertEqual((m["name"], m["method"], m["direction"], m["properties"]), ("BG", "film_offset", "ae2maya", ["pan"]))
        # found by ids even after the layer was renamed
        self.assertIs(lm.find([m], {"comp_id": 12, "layer_id": 345, "comp": "c010", "layer": "BG renamed"}), m)
        self.assertIsNone(lm.find([m], {"comp_id": 12, "layer_id": 346, "comp": "c010", "layer": "BG"}))
        # without ids: by names
        old = lm.new_mapping(dict(AE, comp_id=None, layer_id=None), MAYA)
        self.assertIs(lm.find([old], {"comp": "c010", "layer": "BG"}), old)

    def test_camera_conflicts(self):
        a = lm.new_mapping(AE, MAYA)
        b = lm.new_mapping(dict(AE, layer_id=999, layer="BOOK"), MAYA)
        c = lm.new_mapping(dict(AE, layer_id=1000, layer="BG2"), MAYA, method="pan_zoom")
        self.assertEqual(lm.camera_conflicts([a, b, c], a), [b])     # same camera, same method
        b["enabled"] = False
        self.assertEqual(lm.camera_conflicts([a, b, c], a), [])

    def test_store_round_trip(self):
        a = lm.new_mapping(AE, MAYA)
        stored = lm.dump(lm.upsert([], a))
        self.assertEqual(lm.load(stored), [a])
        a2 = dict(a, method="film_translate")
        self.assertEqual(lm.load(lm.dump(lm.upsert([a], a2)))[0]["method"], "film_translate")
        self.assertEqual(lm.remove([a], a["id"]), [])
        self.assertEqual(lm.load(None), [])
        with self.assertRaises(ValueError):
            lm.load({"schema_version": 99, "mappings": []})

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            lm.new_mapping(AE, MAYA, method="move_camera")
        with self.assertRaises(ValueError):
            lm.new_mapping(AE, dict(MAYA, camera_uuid=""))

    def test_relative_mode_and_reference(self):
        m = lm.new_mapping(AE, dict(MAYA, bg_uuid=None), method="pan_zoom", mode="relative")   # no BG needed
        self.assertEqual((lm.mode_of(m), m["reference"]), ("relative", None))
        self.assertIn(u"基準なし", lm.describe(m))
        r = lm.with_reference(m, [[1, 0, -2040], [0, 1, -1460], [0, 0, 1]], {"hpan": 0.0, "vpan": 0.0}, 0.5)
        self.assertEqual(r["reference"]["camera"], {"hpan": 0.0, "vpan": 0.0})
        self.assertNotIn(u"基準なし", lm.describe(r))
        self.assertIsNone(lm.without_reference(r)["reference"])
        self.assertEqual(lm.load(lm.dump([r]))[0]["reference"]["matrix"][0], [1, 0, -2040])
        with self.assertRaises(ValueError):                 # absolute mode needs the BG
            lm.new_mapping(AE, dict(MAYA, bg_uuid=None), mode="absolute")
        old = dict(m)
        del old["mode"]
        self.assertEqual(lm.mode_of(old), "absolute")        # records made before D-25

    def test_describe_and_export(self):
        self.assertEqual(lm.describe(lm.new_mapping(AE, MAYA, name="BG Slide")),
                         u"BG Slide: AE c010 / BG → BG_CAMShape（絶対・Film Offset）")
        transform, warnings = lm.ae_layer_from_export({"layer": {"position": [1, 2], "anchorPoint": [3, 4],
                                                                 "effects": ["Curves"]}})
        self.assertEqual(transform["position"], [1, 2])
        self.assertEqual(len(warnings), 1)


if __name__ == "__main__":
    unittest.main()
