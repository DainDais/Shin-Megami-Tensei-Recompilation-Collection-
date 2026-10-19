"""Menu font (D/F0014.BIN): RLE 4bpp texture (208x252) holding 1bpp 12x12 glyphs packed in bit planes.

Each glyph code c maps to (u, v, page, plane) via menu_glyph_table.json, dumped from the game's own
glyph table: plane = c // 346, k = c % 346, u = (k // 21) * 12, v = (k % 21) * 12.
The game draws a menu glyph as a 12x12 sprite whose CLUT shows only that bit plane.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rle  # noqa: E402

TABLE = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'menu_glyph_table.json')))


class MenuFont:
    def __init__(self, f0014):
        self.orig = f0014
        self.w, self.h, px, self.used = rle.decode(f0014, 0)
        W = self.w * 4
        self.pix = [[0] * W for _ in range(self.h)]
        for y in range(self.h):
            row = px[y * self.w * 2:(y + 1) * self.w * 2]
            for x in range(W):
                b = row[x // 2]
                self.pix[y][x] = (b >> 4) if x & 1 else (b & 15)

    def get(self, code):
        u, v, page, plane = TABLE[code]
        return [[(self.pix[v + y][u + x] >> plane) & 1 for x in range(12)] for y in range(12)]

    def set(self, code, rows):
        u, v, page, plane = TABLE[code]
        m = 1 << plane
        for y in range(12):
            for x in range(12):
                p = self.pix[v + y][u + x] & ~m
                if rows[y][x]:
                    p |= m
                self.pix[v + y][u + x] = p

    def raw(self):
        W = self.w * 4
        out = bytearray()
        for y in range(self.h):
            for x in range(0, W, 2):
                out.append(self.pix[y][x] | (self.pix[y][x + 1] << 4))
        return bytes(out)

    def build(self):
        """[font image RLE][align 4][following blocks verbatim (palette)], padded to the original size."""
        import struct
        blk = bytearray(rle.encode(self.w, self.h, self.raw()))
        p = (self.used + 3) & ~3
        rest = bytearray()
        while p + 8 <= len(self.orig):
            magic, size = struct.unpack_from('<II', self.orig, p)
            if magic == 0 or size == 0:
                break
            while len(rest) % 4:
                rest.append(0)
            rest += self.orig[p:p + size]
            p = (p + size + 3) & ~3
        while len(blk) % 4:
            blk.append(0)
        out = bytes(blk) + bytes(rest)
        if len(out) > len(self.orig):
            raise ValueError(f'menu font grew past its allocation: {len(out)} > {len(self.orig)}')
        return out + bytes(len(self.orig) - len(out))
