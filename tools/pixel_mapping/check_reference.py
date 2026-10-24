r"""Check rendered frames of the Pixel Mapping test against the core's prediction (B Lite).

    py -3 tools\pixel_mapping\check_reference.py <folder> [--prefix ae_ref_] [--threshold 24]

<folder> holds pixel_mapping_cases.json (written by after_effects/jsx/pixel_mapping_reference.jsx)
and the frames <prefix><frame:04d>.png. For each case the markers of the test BG are expected where
syncbridge.core.pixel_mapping.ae_layer_matrix puts them (H-AE-24); the report shows the errors and
is saved as pixel_mapping_report.json. Standard library only.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
from syncbridge.core import pixel_mapping  # noqa: E402
from syncbridge.pixelcheck import measure, png, testgrid  # noqa: E402

LIMIT_PX = 1.0       # Phase 1 pass: every marker of every frame within 1 px


def check(folder, prefix="ae_ref_", threshold=24):
    with open(os.path.join(folder, "pixel_mapping_cases.json"), encoding="utf-8") as f:
        cases = json.load(f)
    src = cases["source"]
    markers = testgrid.marker_positions(int(src["width"]), int(src["height"]))
    rows = []
    for case in cases["cases"]:
        path = os.path.join(folder, "%s%04d.png" % (prefix, case["frame"]))
        if not os.path.exists(path):
            rows.append({"frame": case["frame"], "missing": path})
            continue
        layer = dict(cases["layer"], position=case["position"])
        m, warnings = pixel_mapping.ae_layer_matrix(layer)
        expected = []
        for mk in markers:
            x, y = pixel_mapping.apply(m, mk["x"], mk["y"])
            expected.append(dict(mk, x=x, y=y))
        img = png.read(path)
        rep = measure.compare(img, expected, search=12, threshold=threshold)
        rows.append({"frame": case["frame"], "position": case["position"], "summary": measure.summary(rep),
                     "max_dist": rep.get("max_dist"), "mean_dx": rep.get("mean_dx"), "mean_dy": rep.get("mean_dy"),
                     "count": rep.get("count"), "corners_ok": rep.get("corners_ok"), "warnings": warnings})
    measured = [r for r in rows if r.get("count")]
    worst = max((r["max_dist"] for r in measured), default=None)
    passed = bool(measured) and len(measured) == len(rows) and worst < LIMIT_PX and all(r["corners_ok"] for r in measured)
    report = {"folder": folder, "aeVersion": cases.get("aeVersion"), "frames": rows, "max_dist": worst,
              "passed": passed, "limit_px": LIMIT_PX}
    with open(os.path.join(folder, "pixel_mapping_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder")
    parser.add_argument("--prefix", default="ae_ref_")
    parser.add_argument("--threshold", type=int, default=24)
    args = parser.parse_args(argv)
    report = check(args.folder, args.prefix, args.threshold)
    for r in report["frames"]:
        if "missing" in r:
            print("frame %d: no image (%s)" % (r["frame"], r["missing"]))
        else:
            print("frame %d position %s: %s" % (r["frame"], r["position"], r["summary"]))
    print("max error %s px -> %s (limit %g px)" % (
        "-" if report["max_dist"] is None else "%.3f" % report["max_dist"], "PASS" if report["passed"] else "FAIL",
        LIMIT_PX))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
