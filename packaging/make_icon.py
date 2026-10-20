"""Make the SyncBridge icons from the source artwork.

    .venv\\Scripts\\python packaging\\make_icon.py

Source: maya_plugin/icons/source/syncbridge_icon.webp (the SyncBridge icon, given by the user
2026-10-20). The transparent / white margin around the rounded square is cut off, then the
image is scaled with smoothing to every size in OUTPUTS. Needs PySide6
(requirements-monitor.txt), which reads WebP and writes ICO.
"""
import os
import struct
import sys

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect, Qt
from PySide6.QtGui import QImage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "maya_plugin", "icons", "source", "syncbridge_icon.webp")
# (file, size, format)
OUTPUTS = [
    (os.path.join(ROOT, "maya_plugin", "icons", "syncbridge_shelf.png"), 32, "PNG"),       # Maya shelf button
    (os.path.join(ROOT, "maya_plugin", "icons", "syncbridge_logo.png"), 64, "PNG"),        # Maya panel, top right
    (os.path.join(ROOT, "src", "syncbridge", "monitor", "syncbridge_icon.png"), 256, "PNG"),  # monitor window
    (os.path.join(ROOT, "packaging", "syncbridge.ico"), 256, "MULTI_ICO"),                 # EXE, Start menu
    (os.path.join(ROOT, "after_effects", "panel", "img", "syncbridge_logo.png"), 64, "PNG"),  # AE panel header
    (os.path.join(ROOT, "after_effects", "panel", "img", "syncbridge_23.png"), 23, "PNG"),    # CEP manifest icon
]


def is_margin(color) -> bool:
    """Transparent or (near) white: the area around the rounded square."""
    return color.alpha() < 16 or (color.red() > 235 and color.green() > 235 and color.blue() > 235)


def content_rect(image: QImage) -> QRect:
    w, h = image.width(), image.height()
    xs, ys = [], []
    step = max(1, min(w, h) // 400)            # enough to find the edges of the square
    for y in range(0, h, step):
        for x in range(0, w, step):
            if not is_margin(image.pixelColor(x, y)):
                xs.append(x)
                ys.append(y)
    if not xs:
        return QRect(0, 0, w, h)
    left, right, top, bottom = min(xs), max(xs), min(ys), max(ys)
    side = max(right - left, bottom - top) + 1    # keep it square
    cx, cy = (left + right) // 2, (top + bottom) // 2
    return QRect(cx - side // 2, cy - side // 2, side, side)


ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def _png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def save_multi_ico(square: QImage, path: str) -> bool:
    """An ICO with every size in ICO_SIZES (PNG entries, Windows Vista+).

    Qt writes one image per ICO; with only 256x256 the Start menu and the task bar kept showing
    the old icon (2026-10-20), so the small sizes are written too.
    """
    images = [_png_bytes(square.scaled(s, s, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)) for s in ICO_SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for size, data in zip(ICO_SIZES, images):
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    with open(path, "wb") as f:
        f.write(header + entries + b"".join(images))
    return True


def main() -> int:
    image = QImage(SOURCE)
    if image.isNull():
        print("cannot read %s" % SOURCE, file=sys.stderr)
        return 1
    image = image.convertToFormat(QImage.Format_ARGB32)
    rect = content_rect(image)
    square = image.copy(rect)
    print("cut %d,%d %dx%d from %dx%d" % (rect.x(), rect.y(), rect.width(), rect.height(),
                                          image.width(), image.height()))
    for path, size, fmt in OUTPUTS:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if fmt == "MULTI_ICO":
            save_multi_ico(square, path)
            print("%s: %s ICO" % (os.path.relpath(path, ROOT), "/".join(str(s) for s in ICO_SIZES)))
            continue
        icon = square.scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        if not icon.save(path, fmt):
            print("cannot write %s" % path, file=sys.stderr)
            return 1
        print("%s: %dx%d %s" % (os.path.relpath(path, ROOT), size, size, fmt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
