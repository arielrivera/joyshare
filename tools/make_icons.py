"""Draws joyshare's app icon with nothing but the standard library and writes PNG files.

The icon: a lime "play" triangle with a hard magenta shadow on a near-black square,
matching the app's default look. Run:  python3 make_icons.py OUTPUT_FOLDER
"""
import struct
import sys
import zlib
from pathlib import Path

BG, SHADOW, FRONT = (7, 5, 13), (255, 47, 146), (200, 255, 46)


def inside(px, py, tri):
    (ax, ay), (bx, by), (cx, cy) = tri
    d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by)
    d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy)
    d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay)
    return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))


def render(size, scale):
    """scale = how much of the square the triangle fills (smaller for 'maskable' icons that get cropped)."""
    ss = 3  # samples per pixel side, for smooth edges
    c, r = 0.5, 0.30 * scale
    front = [(c - r * 0.78, c - r), (c - r * 0.78, c + r), (c + r * 1.0, c)]
    off = 0.055 * scale
    shadow = [(x + off, y + off) for x, y in front]
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            acc = [0, 0, 0]
            for sy in range(ss):
                for sx in range(ss):
                    px, py = (x + (sx + 0.5) / ss) / size, (y + (sy + 0.5) / ss) / size
                    color = FRONT if inside(px, py, front) else SHADOW if inside(px, py, shadow) else BG
                    acc[0] += color[0]; acc[1] += color[1]; acc[2] += color[2]
            row += bytes(v // (ss * ss) for v in acc)
        rows.append(bytes(row))
    return b"".join(rows)


def png(size, pixels):
    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(pixels, 9)) + chunk(b"IEND", b"")


out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
for name, size, scale in (("icon-192.png", 192, 1.0), ("icon-512.png", 512, 1.0),
                          ("icon-maskable-512.png", 512, 0.72), ("apple-touch-icon.png", 180, 0.92)):
    (out / name).write_bytes(png(size, render(size, scale)))
    print(name, size)
