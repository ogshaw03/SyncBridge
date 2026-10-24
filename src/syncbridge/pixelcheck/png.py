"""Minimal PNG reading and writing (8-bit gray / RGB / RGBA, no interlace), standard library only.

    img = png.read("render.png")      # Image(width, height, channels, rows: list of bytearray)
    png.write("bg.png", img)
"""
from __future__ import annotations

import struct
import zlib
from typing import List

SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}       # PNG color type -> channels (gray, RGB, gray+alpha, RGBA)
COLOR_TYPE = {1: 0, 2: 4, 3: 2, 4: 6}


class Image:
    """8-bit image; rows[y][x * channels + c]."""

    def __init__(self, width: int, height: int, channels: int = 3, rows: List[bytearray] = None, fill: int = 0):
        self.width, self.height, self.channels = width, height, channels
        self.rows = rows if rows is not None else [bytearray([fill]) * (width * channels) for _ in range(height)]

    def get(self, x: int, y: int) -> tuple:
        i = x * self.channels
        return tuple(self.rows[y][i:i + self.channels])

    def set(self, x: int, y: int, color) -> None:
        i = x * self.channels
        self.rows[y][i:i + self.channels] = bytes(color[:self.channels])

    def fill_rect(self, x0: int, y0: int, x1: int, y1: int, color) -> None:
        """Pixels x0 <= x < x1, y0 <= y < y1 (clipped)."""
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(self.width, x1), min(self.height, y1)
        if x1 <= x0 or y1 <= y0:
            return
        span = bytes(color[:self.channels]) * (x1 - x0)
        for y in range(y0, y1):
            self.rows[y][x0 * self.channels:x1 * self.channels] = span


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def write(path: str, img: Image, level: int = 6) -> None:
    header = struct.pack(">IIBBBBB", img.width, img.height, 8, COLOR_TYPE[img.channels], 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(row) for row in img.rows)          # filter type 0 on every row
    with open(path, "wb") as f:
        f.write(SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(raw, level))
                + _chunk(b"IEND", b""))


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def read(path: str) -> Image:
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != SIGNATURE:
        raise ValueError("%s is not a PNG file" % path)
    pos, idat, header = 8, [], None
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
        pos += 12 + length
    width, height, depth, color_type, _comp, _filter, interlace = header
    if depth != 8 or interlace != 0 or color_type not in CHANNELS:
        raise ValueError("%s: only 8-bit, non-interlaced gray / RGB / RGBA PNG is supported" % path)
    channels = CHANNELS[color_type]
    raw = zlib.decompress(b"".join(idat))
    stride = width * channels
    rows, prev, i = [], bytearray(stride), 0
    for _y in range(height):
        kind = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        if kind == 1:
            for x in range(channels, stride):
                line[x] = (line[x] + line[x - channels]) & 0xFF
        elif kind == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 0xFF
        elif kind == 3:
            for x in range(stride):
                left = line[x - channels] if x >= channels else 0
                line[x] = (line[x] + ((left + prev[x]) >> 1)) & 0xFF
        elif kind == 4:
            for x in range(stride):
                left = line[x - channels] if x >= channels else 0
                up_left = prev[x - channels] if x >= channels else 0
                line[x] = (line[x] + _paeth(left, prev[x], up_left)) & 0xFF
        rows.append(line)
        prev = line
    return Image(width, height, channels, rows)
