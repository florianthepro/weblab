"""Markenzeichen als PNG/ICO/SVG — ohne Bibliotheken gerechnet."""
import struct
import zlib

BG_TOP = (10, 132, 255)
BG_BOTTOM = (94, 92, 230)
STROKE = [(0.215, 0.345), (0.360, 0.690), (0.500, 0.455), (0.640, 0.690), (0.785, 0.345)]
STROKE_W = 0.088
RADIUS = 0.225
SIZES = (64, 180, 512)
_CACHE = {}


def _dist_to_segment(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    span = dx * dx + dy * dy
    t = 0.0 if span == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / span))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def _coverage(x, y):
    """Deckung an Position 0..1: (Hintergrund, Glyph)."""
    r = RADIUS
    cx = min(max(x, r), 1 - r)
    cy = min(max(y, r), 1 - r)
    inside = 1.0 if ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 <= r else 0.0
    glyph = 0.0
    if inside:
        near = min(_dist_to_segment(x, y, *STROKE[i], *STROKE[i + 1])
                   for i in range(len(STROKE) - 1))
        glyph = 1.0 if near <= STROKE_W / 2 else 0.0
    return inside, glyph


def rgba_rows(size, samples=3):
    rows = []
    step = 1.0 / (size * samples)
    for py in range(size):
        row = bytearray()
        for px in range(size):
            bg_hits = glyph_hits = 0
            for sy in range(samples):
                for sx in range(samples):
                    x = (px * samples + sx + 0.5) * step
                    y = (py * samples + sy + 0.5) * step
                    inside, glyph = _coverage(x, y)
                    bg_hits += inside
                    glyph_hits += glyph
            total = samples * samples
            alpha = bg_hits / total
            if alpha == 0:
                row += b"\x00\x00\x00\x00"
                continue
            mix = py / max(1, size - 1)
            base = [round(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * mix) for i in range(3)]
            g = glyph_hits / total
            color = [round(base[i] + (255 - base[i]) * g) for i in range(3)]
            row += bytes(color) + bytes([round(alpha * 255)])
        rows.append(bytes(row))
    return rows


def _chunk(kind, payload):
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))


def png_bytes(size=180):
    if size in _CACHE:
        return _CACHE[size]
    raw = b"".join(b"\x00" + row for row in rgba_rows(size))
    data = (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw, 9))
            + _chunk(b"IEND", b""))
    _CACHE[size] = data
    return data


def warm():
    for size in SIZES:
        png_bytes(size)


def _dib_bytes(size):
    """Klassischer BMP-Eintrag (unten nach oben, BGRA) — Windows zeigt kleine
    Symbolgroessen aus PNG-Eintraegen nicht ueberall zuverlaessig."""
    rows = rgba_rows(size)
    pixels = bytearray()
    for row in reversed(rows):
        for x in range(size):
            r, g, b, a = row[x * 4:x * 4 + 4]
            pixels += bytes((b, g, r, a))
    mask_stride = ((size + 31) // 32) * 4
    mask = bytes(mask_stride * size)
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                         len(pixels) + len(mask), 0, 0, 0, 0)
    return header + bytes(pixels) + mask


def ico_bytes(sizes=(16, 32, 48, 256)):
    """Symbol mit mehreren Groessen: Windows skaliert sonst 256 px auf 16 px herunter."""
    if isinstance(sizes, int):
        sizes = (sizes,)
    images = []
    for size in sizes:
        if not 1 <= size <= 256:
            raise ValueError("ICO-Groessen liegen zwischen 1 und 256")
        images.append((size, png_bytes(size) if size == 256 else _dib_bytes(size)))
    offset = 6 + 16 * len(images)
    head = struct.pack("<HHH", 0, 1, len(images))
    entries, blobs = b"", b""
    for size, blob in images:
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32,
                               len(blob), offset)
        offset += len(blob)
        blobs += blob
    return head + entries + blobs


def svg():
    pts = " ".join(f"{x * 100:.1f},{y * 100:.1f}" for x, y in STROKE)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="rgb{BG_TOP}"/>'
        f'<stop offset="1" stop-color="rgb{BG_BOTTOM}"/></linearGradient></defs>'
        f'<rect width="100" height="100" rx="{RADIUS * 100:.0f}" fill="url(#g)"/>'
        f'<polyline points="{pts}" fill="none" stroke="#fff" '
        f'stroke-width="{STROKE_W * 100:.1f}" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>")
