"""Pixel accuracy check tools (B Lite): PNG, test BG, marker measurement."""
import os
import shutil
import tempfile
import unittest

from syncbridge.pixelcheck import measure, png, testgrid


class PngTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_round_trip(self):
        img = png.Image(7, 5, 3, fill=10)
        img.set(3, 2, (200, 100, 50))
        img.fill_rect(0, 4, 7, 5, (1, 2, 3))
        path = os.path.join(self.tmp, "a.png")
        png.write(path, img)
        back = png.read(path)
        self.assertEqual((back.width, back.height, back.channels), (7, 5, 3))
        self.assertEqual(back.get(3, 2), (200, 100, 50))
        self.assertEqual(back.get(6, 4), (1, 2, 3))
        self.assertEqual(back.get(0, 0), (10, 10, 10))

    def test_filtered_rows_are_decoded(self):
        # rows written with Sub / Up / Average / Paeth filters by hand
        import struct
        import zlib
        rows = [bytes([1, 2, 3, 4, 5, 6]), bytes([7, 8, 9, 10, 11, 12]), bytes([3, 3, 3, 9, 9, 9]),
                bytes([0, 50, 100, 150, 200, 250])]
        prev = bytes(6)
        raw = b""
        for kind, row in zip((1, 2, 3, 4), rows):
            enc = bytearray(6)
            for x in range(6):
                left = row[x - 3] if x >= 3 else 0
                up = prev[x]
                ul = prev[x - 3] if x >= 3 else 0
                pred = {1: left, 2: up, 3: (left + up) >> 1, 4: png._paeth(left, up, ul)}[kind]
                enc[x] = (row[x] - pred) & 0xFF
            raw += bytes([kind]) + bytes(enc)
            prev = row
        path = os.path.join(self.tmp, "f.png")
        with open(path, "wb") as f:
            f.write(png.SIGNATURE + png._chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 4, 8, 2, 0, 0, 0))
                    + png._chunk(b"IDAT", zlib.compress(raw)) + png._chunk(b"IEND", b""))
        img = png.read(path)
        self.assertEqual([bytes(r) for r in img.rows], rows)


class MarkerTest(unittest.TestCase):
    def test_markers_are_found_where_they_are(self):
        img = testgrid.make(1000, 600, step=200)
        expected = testgrid.marker_positions(1000, 600, step=200)
        self.assertEqual(expected[0]["x"], 100.5)                 # center of the 9 x 9 square at pixel 100
        report = measure.compare(img, expected)
        self.assertEqual(report["count"], len(expected))
        self.assertLess(report["max_dist"], 1e-9)
        self.assertTrue(report["corners_ok"])

    def test_shifted_copy_reports_the_shift(self):
        src = testgrid.make(1000, 600, step=200)
        shifted = png.Image(1000, 600, 3)
        for y in range(600):                                       # content moved 3 px right, 2 px up
            sy = y + 2
            if 0 <= sy < 600:
                shifted.rows[y][3 * 3:] = src.rows[sy][:(1000 - 3) * 3]
        report = measure.compare(shifted, testgrid.marker_positions(1000, 600, step=200))
        self.assertAlmostEqual(report["mean_dx"], 3.0)
        self.assertAlmostEqual(report["mean_dy"], -2.0)

    def test_half_pixel_shift_gives_a_half_pixel(self):
        # a 9 px square covering [10.5, 19.5) x [10, 19): the edge columns are half covered
        img = png.Image(40, 40, 3)
        img.fill_rect(11, 10, 19, 19, (255, 255, 255))
        img.fill_rect(10, 10, 11, 19, (200, 200, 200))
        img.fill_rect(19, 10, 20, 19, (200, 200, 200))
        found = measure.find_marker(img, 14.5, 14.5)
        self.assertAlmostEqual(found["x"], 15.0)
        self.assertAlmostEqual(found["y"], 14.5)


def _load_tool(name):
    import importlib.util
    path = os.path.join(os.path.dirname(__file__), "..", "..", "tools", "pixel_mapping", name + ".py")
    spec = importlib.util.spec_from_file_location("pm_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _render_like_ae(src, comp_w, comp_h, ox, oy):
    """A 2D layer at offset (ox, oy) = position - anchor, bilinear resampling (what AE is expected to do)."""
    out = png.Image(comp_w, comp_h, 3)
    for j in range(comp_h):
        v = j + 0.5 - oy - 0.5
        j0 = int(v // 1)
        fy = v - j0
        for i in range(comp_w):
            u = i + 0.5 - ox - 0.5
            i0 = int(u // 1)
            fx = u - i0
            acc = [0.0, 0.0, 0.0]
            for (di, dj, w) in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy),
                                (1, 1, fx * fy)):
                si, sj = i0 + di, j0 + dj
                if w and 0 <= si < src.width and 0 <= sj < src.height:
                    px = src.get(si, sj)
                    for c in range(3):
                        acc[c] += w * px[c]
            out.set(i, j, [int(round(a)) for a in acc])
    return out


class CheckReferenceToolTest(unittest.TestCase):
    def test_frames_rendered_like_ae_pass(self):
        import json
        tool = _load_tool("check_reference")
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        src = testgrid.make(1000, 600)             # the tool uses the default marker step
        cases = [[200.0, 150.0], [137.0, 260.0], [200.5, 150.25]]
        for frame, (x, y) in enumerate(cases):
            png.write(os.path.join(tmp, "ae_ref_%04d.png" % frame), _render_like_ae(src, 400, 300, x - 500.0, y - 300.0))
        with open(os.path.join(tmp, "pixel_mapping_cases.json"), "w") as f:
            json.dump({"comp": {"width": 400, "height": 300, "pixelAspect": 1.0},
                       "source": {"width": 1000, "height": 600},
                       "layer": {"anchorPoint": [500.0, 300.0], "scale": [100, 100], "rotation": 0},
                       "cases": [{"frame": i, "position": c} for i, c in enumerate(cases)]}, f)
        report = tool.check(tmp)
        self.assertTrue(report["passed"], report)
        self.assertLess(report["max_dist"], 0.05)
        self.assertTrue(os.path.exists(os.path.join(tmp, "pixel_mapping_report.json")))


if __name__ == "__main__":
    unittest.main()
