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

    def test_change_method(self):
        rel = lm.with_reference(lm.new_mapping(AE, MAYA, method="pan_zoom", mode="relative"),
                                [[1, 0, 0], [0, 1, 0], [0, 0, 1]], {"hpan": 0.0}, 0.0)
        changed = lm.with_method(rel, "film_roll")
        self.assertEqual((changed["method"], changed["reference"]), ("film_roll", None))   # new reference next time
        absolute = lm.with_method(lm.new_mapping(AE, MAYA), "film_translate")
        self.assertEqual(absolute["method"], "film_translate")
        self.assertIn(u"Film Translate・Scale・Roll", lm.describe(changed))
        with self.assertRaises(ValueError):
            lm.with_method(rel, "camera_move")

    def test_schema1_store_gets_one_maya_layer_per_camera(self):
        a = lm.new_mapping(AE, MAYA)
        b = lm.new_mapping(dict(AE, layer_id=2, layer="BOOK"), MAYA)
        c = lm.new_mapping(dict(AE, layer_id=3, layer="CHAR"), dict(MAYA, camera_uuid="CAM2", camera="|C|CAM2Shape"))
        store = lm.load_store({"schema_version": 1, "mappings": [a, b, c]})
        self.assertEqual(len(store["maya_layers"]), 2)
        names = sorted(layer["name"] for layer in store["maya_layers"])
        self.assertEqual(names, ["BG_CAM", "CAM2"])
        self.assertEqual(store["mappings"][0]["maya_layer"], store["mappings"][1]["maya_layer"])
        back = lm.load_store(lm.dump_store(store))
        self.assertEqual(back["maya_layers"], store["maya_layers"])
        self.assertEqual(lm.dump_store(store)["schema_version"], 2)

    def test_maya_layers_and_wires(self):
        store = lm.empty_store()
        bg = lm.new_maya_layer("BG", "CAM-UUID", "|BG_CAM|BG_CAMShape")
        book = lm.new_maya_layer("BOOK")                       # no camera yet
        store["maya_layers"] += [bg, book]
        link = lm.connect(store, AE, bg["id"], method="film_roll", mode="relative")
        self.assertEqual((link["maya_layer"], link["maya"]["camera_uuid"]), (bg["id"], "CAM-UUID"))
        with self.assertRaises(ValueError):                     # a Maya layer without a camera
            lm.connect(store, dict(AE, layer_id=2), book["id"])
        lm.set_layer_camera(store, book["id"], "CAM-B", "|BOOK_CAM|BOOK_CAMShape")
        link["reference"] = {"matrix": [], "camera": {}}
        moved = lm.connect(store, AE, book["id"])                # the same AE layer: the wire moves
        self.assertIs(moved, link)
        self.assertEqual((len(store["mappings"]), link["maya_layer"], link["reference"]), (1, book["id"], None))
        link["reference"] = {"matrix": [], "camera": {}}
        lm.set_layer_camera(store, book["id"], "CAM-C", "|C|CShape")      # camera changed: reference dropped
        self.assertEqual((link["maya"]["camera_uuid"], link["reference"]), ("CAM-C", None))
        self.assertEqual(lm.links_of(store, book["id"]), [link])
        self.assertEqual(lm.remove_maya_layer(store, book["id"]), 1)
        self.assertEqual((store["mappings"], [layer["id"] for layer in store["maya_layers"]]), ([], [bg["id"]]))

    def test_layer_for_camera(self):
        store = lm.empty_store()
        first = lm.layer_for_camera(store, "CAM-UUID", "|BG_CAM|BG_CAMShape")
        self.assertIs(lm.layer_for_camera(store, "CAM-UUID"), first)
        self.assertEqual((first["name"], len(store["maya_layers"])), ("BG_CAM", 1))

    def test_layers_info_and_mode(self):
        comp = {"id": 12, "name": "c010"}
        layer = {"id": 345, "name": "BG", "source": "bg.png", "width": 6000, "height": 4000, "kind": "still"}
        self.assertEqual(lm.ae_from_layers_info(comp, layer), AE)
        rel = lm.with_reference(lm.new_mapping(AE, dict(MAYA, bg_uuid=None, bg=None), mode="relative"),
                                [[1, 0, 0], [0, 1, 0], [0, 0, 1]], {}, 0.0)
        with self.assertRaises(ValueError):                 # absolute needs a BG
            lm.with_mode(rel, "absolute")
        absolute = lm.with_mode(rel, "absolute", {"uuid": "BG-2", "name": "|plane2"})
        self.assertEqual((absolute["mode"], absolute["maya"]["bg_uuid"], absolute["reference"]),
                         ("absolute", "BG-2", None))
        self.assertEqual(lm.with_mode(absolute, "relative")["maya"]["bg_uuid"], "BG-2")   # the BG is kept
        with self.assertRaises(ValueError):
            lm.with_mode(rel, "sideways")

    def test_describe_and_export(self):
        self.assertEqual(lm.describe(lm.new_mapping(AE, MAYA, name="BG Slide")),
                         u"BG Slide: AE c010 / BG → BG_CAMShape（絶対・Film Offset）")
        transform, warnings = lm.ae_layer_from_export({"layer": {"position": [1, 2], "anchorPoint": [3, 4],
                                                                 "effects": ["Curves"]}})
        self.assertEqual(transform["position"], [1, 2])
        self.assertEqual(len(warnings), 1)


if __name__ == "__main__":
    unittest.main()
