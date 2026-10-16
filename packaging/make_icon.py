"""Generate the Maya shelf icon (32x32 PNG, standard library only).

    py -3 packaging\\make_icon.py  ->  maya_plugin/icons/syncbridge_shelf.png

A rounded square with two arrows pointing at each other (Maya <-> AE).
"""
import os
import struct
import zlib

SIZE = 32
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "maya_plugin", "icons", "syncbridge_shelf.png")
BG = (45, 140, 235)
FG = (255, 255, 255)


def inside_rounded_square(x, y, r=6.0, pad=1.0):
    lo, hi = pad, SIZE - 1 - pad
    cx = min(max(x, lo + r), hi - r)
    cy = min(max(y, lo + r), hi - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r and lo <= x <= hi and lo <= y <= hi


def on_arrow(x, y):
    # upper arrow pointing right (y = 11), lower arrow pointing left (y = 20)
    for row, head_x, direction in ((11, 25, 1), (20, 6, -1)):
        x0, x1 = (7, 22) if direction == 1 else (9, 24)
        if x0 <= x <= x1 and abs(y - row) <= 1:
            return True
        dx = (head_x - x) * direction
        if 0 <= dx <= 5 and abs(y - row) <= dx:
            return True
    return False


def pixel(x, y):
    if not inside_rounded_square(x + 0.5, y + 0.5):
        return (0, 0, 0, 0)
    if on_arrow(x, y):
        return FG + (255,)
    return BG + (255,)


def png(width, height, rows):
    def chunk(kind, data):
        body = kind + data
        return struct.pack("!I", len(data)) + body + struct.pack("!I", zlib.crc32(body) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes(v for px in row for v in px) for row in rows)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def main():
    rows = [[pixel(x, y) for x in range(SIZE)] for y in range(SIZE)]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(png(SIZE, SIZE, rows))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
