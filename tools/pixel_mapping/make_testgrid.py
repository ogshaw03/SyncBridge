r"""Write the Pixel Mapping test BG (docs/PIXEL_MAPPING.md).

    py -3 tools\pixel_mapping\make_testgrid.py [out.png] [width height]

Default: testgrid_6000x4000.png in the current folder (about 0.6 MB). Standard library only.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
from syncbridge.pixelcheck import png, testgrid  # noqa: E402


def main(argv):
    out = argv[1] if len(argv) > 1 else "testgrid_6000x4000.png"
    width, height = (int(argv[2]), int(argv[3])) if len(argv) > 3 else (6000, 4000)
    png.write(out, testgrid.make(width, height))
    print("wrote %s (%dx%d, %d markers)" % (out, width, height, len(testgrid.marker_positions(width, height))))


if __name__ == "__main__":
    main(sys.argv)
