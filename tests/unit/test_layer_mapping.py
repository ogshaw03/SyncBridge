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

    def test_dedicated_camera(self):
        # D-29: links move the layer's dedicated camera; a layer without one (schema 1) moves its camera
        store = lm.empty_store()
        bg = lm.new_maya_layer("BG", "SHOT", "|SHOT_CAM|SHOT_CAMShape", layer_camera_uuid="SB-BG",
                               layer_camera="|SHOT_CAM|SB_BG_CAM|SB_BG_CAMShape")
        char = lm.new_maya_layer("CHAR", "SHOT", "|SHOT_CAM|SHOT_CAMShape", layer_camera_uuid="SB-CHAR",
                                 layer_camera="|SHOT_CAM|SB_CHAR_CAM|SB_CHAR_CAMShape")
        store["maya_layers"] += [bg, char]
        a = lm.connect(store, AE, bg["id"], method="pan_zoom")
        b = lm.connect(store, dict(AE, layer_id=2, layer="CHAR"), char["id"], method="pan_zoom")
        self.assertEqual((a["maya"]["camera_uuid"], b["maya"]["camera_uuid"]), ("SB-BG", "SB-CHAR"))
        self.assertEqual(lm.camera_conflicts(store["mappings"], a), [])      # same original, no conflict
        a["reference"] = {"matrix": [], "camera": {}}
        lm.set_layer_camera(store, bg["id"], "SHOT", "|SHOT_CAM|SHOT_CAMShape", "SB-BG", "|SHOT_CAM|SB_BG2_CAM|S")
        self.assertEqual((a["maya"]["camera"], a["reference"] is not None), ("|SHOT_CAM|SB_BG2_CAM|S", True))
        lm.set_layer_camera(store, bg["id"], "ALT", "|ALT|ALTShape", "SB-BG", "|ALT|SB_BG_CAM|S")
        self.assertIsNone(a["reference"])                                    # another original camera
        legacy = lm.new_maya_layer("OLD", "CAM-UUID", "|BG_CAM|BG_CAMShape")
        self.assertEqual(lm.driven_camera(legacy), {"camera_uuid": "CAM-UUID", "camera": "|BG_CAM|BG_CAMShape"})

    def test_view_camera_does_not_follow_visibility(self):
        # the viewer's camera (and its comp frame) stays when the top layer is hidden (the user, 2026-10-26)
        store = lm.empty_store()
        none = lm.new_maya_layer("FX")
        char = lm.new_maya_layer("CHAR", "SHOT", "|SHOT", [{"uuid": "c1", "name": "|char"}], "SB-CHAR", "|SB_CHAR")
        bg = lm.new_maya_layer("BG", "PLATE", "|PLATE", [{"uuid": "t1", "name": "|town"}], "SB-BG", "|SB_BG")
        store["maya_layers"] += [none, char, bg]
        self.assertEqual(lm.view_camera_uuid(store), "SHOT")
        char["visible"] = False
        self.assertEqual(lm.view_camera_uuid(store), "SHOT")
        self.assertIsNone(lm.view_camera_uuid(lm.empty_store()))

    def test_stack_order(self):
        # D-32: the first layer in the layer map is on top (drawn last); no camera / no objects -> left out
        store = lm.empty_store()
        top = lm.new_maya_layer("CHAR", "SHOT", "|SHOT", [{"uuid": "c1", "name": "|char"}], "SB-CHAR", "|SB_CHAR")
        none = lm.new_maya_layer("EMPTY", "SHOT", "|SHOT", [])
        bottom = lm.new_maya_layer("BG", "SHOT", "|SHOT", [{"uuid": "t1", "name": "|town"}, {"uuid": "t2", "name": "|sky"}],
                                   "SB-BG", "|SB_BG")
        store["maya_layers"] += [top, none, bottom]
        self.assertEqual([(s["name"], s["camera_uuid"], s["object_uuids"]) for s in lm.stack(store)],
                         [("BG", "SB-BG", ["t1", "t2"]), ("CHAR", "SB-CHAR", ["c1"])])
        # D-33: any order; hidden layers are not drawn
        lm.reorder_layers(store, [bottom["id"], top["id"]])
        self.assertEqual([layer["name"] for layer in store["maya_layers"]], ["BG", "CHAR", "EMPTY"])
        self.assertEqual([s["name"] for s in lm.stack(store)], ["CHAR", "BG"])
        lm.set_layer_visible(store, top["id"], False)
        self.assertEqual([s["name"] for s in lm.stack(store)], ["BG"])
        self.assertFalse(lm.load_store(lm.dump_store(store))["maya_layers"][1]["visible"])

    def test_layer_for_camera(self):
        store = lm.empty_store()
        first = lm.layer_for_camera(store, "CAM-UUID", "|BG_CAM|BG_CAMShape")
        self.assertIs(lm.layer_for_camera(store, "CAM-UUID"), first)
        self.assertEqual((first["name"], len(store["maya_layers"])), ("BG_CAM", 1))

    def test_layers_info_and_mode(self):
        comp = {"id": 12, "name": "c010"}
        layer = {"id": 345, "name": "BG", "source": "bg.png", "width": 6000, "height": 4000, "kind": "still"}
        self.assertEqual(lm.ae_from_layers_info(comp, layer), dict(AE, via=[]))
        # D-37: a layer inside a precomp names its own comp and the precomp layer above it
        inner = dict(layer, id=9, comp_id=40, comp="SC_PRE", via=[{"comp_id": 12, "comp": "c010", "layer_id": 7,
                                                                   "layer": "SC_PRE"}])
        ae_inner = lm.ae_from_layers_info(comp, inner)
        self.assertEqual((ae_inner["comp_id"], ae_inner["comp"], len(ae_inner["via"])), (40, "SC_PRE", 1))
        link = lm.new_mapping(ae_inner, {"camera_uuid": "C"}, mode="relative")
        self.assertTrue(lm.matches(link, ae_inner))
        self.assertFalse(lm.matches(link, dict(ae_inner, via=[])))           # the same precomp used elsewhere
        self.assertFalse(lm.matches(lm.new_mapping(AE, MAYA), ae_inner))
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


class AeOnTheMapTest(unittest.TestCase):
    """D-40: the layer map shows the AE layers put on it (from the selection in AE) and the linked ones."""

    MAIN = {"id": 12, "name": "c010"}
    PRE = [{"comp_id": 12, "comp": "c010", "layer_id": 9, "layer": "SC_PRE"}]

    def info(self):
        # layersInfo() of the main comp while the precomp SC_PRE (used twice) is open with BG selected
        bg = {"id": 345, "name": "BG", "comp_id": 40, "comp": "SC", "kind": "still", "selected": True}
        return {"comp": dict(self.MAIN), "active": {"id": 40, "name": "SC"}, "layers": [
            {"id": 9, "name": "SC_PRE", "comp_id": 12, "comp": "c010", "kind": "comp", "via": [], "selected": False},
            dict(bg, via=self.PRE),
            {"id": 10, "name": "SC_PRE2", "comp_id": 12, "comp": "c010", "kind": "comp", "via": [], "selected": False},
            dict(bg, via=[dict(self.PRE[0], layer_id=10, layer="SC_PRE2")]),
            {"id": 7, "name": "CHAR", "comp_id": 12, "comp": "c010", "kind": "sequence", "via": [], "selected": False}]}

    def test_the_selection_keeps_its_path_from_the_main_comp(self):
        aes = lm.selected_in_ae(self.info())
        self.assertEqual([(a["layer"], [v["layer"] for v in a["via"]]) for a in aes],
                         [("BG", ["SC_PRE"]), ("BG", ["SC_PRE2"])])      # one per path
        store = lm.empty_store()
        self.assertEqual(lm.show_ae(store, aes), 2)
        self.assertEqual(lm.show_ae(store, aes), 0)                      # already on the map
        self.assertEqual(lm.main_comp(store), self.MAIN)                 # the top comp, not the precomp

    def test_an_added_ae_layer_gets_its_own_linked_maya_layer(self):
        # D-43: one Maya layer per AE layer, source camera mode, Film Translate・Scale・Roll; the camera comes later
        store = lm.empty_store()
        aes = lm.selected_in_ae(self.info())
        links = [lm.add_linked_layer(store, ae) for ae in aes]
        self.assertEqual(len(store["maya_layers"]), 2)
        self.assertEqual([layer["name"] for layer in store["maya_layers"]], ["BG", "BG"])
        for link, layer in zip(links, store["maya_layers"]):
            self.assertEqual((link["mode"], link["method"], link["maya_layer"]), ("source", "film_roll", layer["id"]))
            self.assertFalse(lm.has_camera(link))
            self.assertEqual(lm.camera_conflicts(store["mappings"], link), [])   # no camera: no conflict
        self.assertIn(u"カメラ未設定", lm.describe(links[0]))
        self.assertIsNone(lm.add_linked_layer(store, aes[0]))           # linked already: nothing new
        self.assertEqual(len(store["maya_layers"]), 2)
        self.assertEqual(lm.shown_keys(store), set(lm.ae_key(a) for a in aes))
        self.assertEqual(lm.stack(store), [])                            # no camera, no objects: not drawn
        # the camera set by hand: the link follows the dedicated camera
        layer = store["maya_layers"][0]
        lm.set_layer_camera(store, layer["id"], "CAM", "|CAM|CAMShape", "OWN", "|CAM|SB_BG_CAM|SB_BG_CAMShape")
        self.assertTrue(lm.has_camera(links[0]))
        self.assertEqual(links[0]["maya"]["camera_uuid"], "OWN")
        self.assertFalse(lm.has_camera(links[1]))
        with self.assertRaises(ValueError):                              # a normal link still needs a camera
            lm.new_mapping(aes[0], {}, "film_translate", mode="source")
        with self.assertRaises(ValueError):                              # and a relative one its layer's camera
            lm.connect(store, dict(AE, layer_id=99), store["maya_layers"][1]["id"], mode="relative")

    def test_a_maya_layer_of_the_same_name_is_used(self):
        # made by hand (or by the test scene) before the AE layer was added: linked, not doubled
        store = lm.empty_store()
        own = lm.new_maya_layer("BG", "CAM", "|CAM|CAMShape")
        store["maya_layers"].append(own)
        link = lm.add_linked_layer(store, dict(AE, layer="BG"))
        self.assertEqual(len(store["maya_layers"]), 1)
        self.assertEqual((link["maya_layer"], link["maya"]["camera_uuid"]), (own["id"], "CAM"))
        other = lm.add_linked_layer(store, dict(AE, layer_id=2, layer="BG"))    # BG is linked now: a new one
        self.assertEqual(len(store["maya_layers"]), 2)
        self.assertNotEqual(other["maya_layer"], own["id"])

    def test_take_off_and_linked_ones(self):
        store = lm.empty_store()
        layer = lm.new_maya_layer("BG", "CAM", "|CAM|CAMShape")
        store["maya_layers"].append(layer)
        bg, char = lm.selected_in_ae(self.info())[0], dict(AE, layer_id=7, layer="CHAR")
        lm.show_ae(store, [char])
        lm.connect(store, bg, layer["id"])                               # a link puts it on the map too
        self.assertEqual(lm.shown_keys(store), {lm.ae_key(bg), lm.ae_key(char)})
        with self.assertRaises(ValueError):
            lm.hide_ae(store, lm.ae_key(bg))                             # disconnect first
        lm.hide_ae(store, lm.ae_key(char))
        lm.disconnect(store, store["mappings"][0]["id"])
        self.assertEqual(lm.shown_keys(store), {lm.ae_key(bg)})          # stays after disconnecting
        back = lm.load_store(lm.dump_store(store))
        self.assertEqual(lm.shown_keys(back), {lm.ae_key(bg)})
        self.assertEqual(lm.load_store({"schema_version": 2, "maya_layers": [], "mappings": []})["ae_shown"], [])

    def test_no_main_comp_yet(self):
        self.assertIsNone(lm.main_comp(lm.empty_store()))

    def test_links_recorded_in_a_precomp_get_their_path(self):
        # the user, 2026-10-26: CHA and BG linked while "コンポ 1" (a precomp moved for the camera PAN in
        # the outer comp) was open -> the PAN was missing. The outer comp is made the main comp.
        store = lm.empty_store()
        layer = lm.new_maya_layer("BG", "CAM", "|CAM|CAMShape")
        store["maya_layers"].append(layer)
        inner = {"id": 1, "name": u"コンポ 1"}
        bg = lm.ae_from_layers_info(inner, {"id": 5, "name": "BG"})
        cha = lm.ae_from_layers_info(inner, {"id": 6, "name": "CHA"})
        lm.connect(store, bg, layer["id"], mode="source")
        lm.connect(store, cha, layer["id"], mode="relative")["reference"] = {"matrix": [], "comp_time": 0}
        self.assertEqual(lm.main_comp(store), inner)                    # guessed from the links
        outer = {"id": 30, "name": "MAIN"}
        lm.set_main_comp(store, outer)
        self.assertTrue(lm.outside_main(store, bg))
        via = [{"comp_id": 30, "comp": "MAIN", "layer_id": 2, "layer": u"コンポ 1"}]
        info = {"comp": dict(outer), "layers": [
            {"id": 2, "name": u"コンポ 1", "comp_id": 30, "comp": "MAIN", "kind": "comp", "via": []},
            {"id": 5, "name": "BG", "comp_id": 1, "comp": u"コンポ 1", "kind": "still", "via": via},
            {"id": 6, "name": "CHA", "comp_id": 1, "comp": u"コンポ 1", "kind": "sequence", "via": via}]}
        found = lm.reroutes(store, info)
        self.assertEqual(([f[1]["layer"] for f in found["fix"]], found["many"], found["missing"]), (["BG", "CHA"], [], []))
        self.assertEqual(lm.reroute(store, found["fix"]), 2)
        self.assertEqual([[v["layer"] for v in m["ae"]["via"]] for m in store["mappings"]], [[u"コンポ 1"]] * 2)
        self.assertFalse(any(lm.outside_main(store, m["ae"]) for m in store["mappings"]))
        self.assertIsNone(store["mappings"][1]["reference"])             # relative: record it again
        self.assertEqual(lm.shown_keys(store), set(lm.ae_key(m["ae"]) for m in store["mappings"]))
        self.assertEqual(lm.reroutes(store, info)["fix"], [])
        self.assertEqual(lm.load_store(lm.dump_store(store))["main_comp"], outer)


if __name__ == "__main__":
    unittest.main()
