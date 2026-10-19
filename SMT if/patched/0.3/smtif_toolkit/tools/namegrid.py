#!/usr/bin/env python3
"""English name-entry keyboard picture for D/F0073.BIN.

The name screen does not draw its keyboard from text: it loads F0073, an RLE 0x102
picture (39 halfwords x 208 = 156x208 at 4 bpp) holding the 13 x 16 character grid
(12 px cells, white ink + dark shadow), the cursor sprites and "-END-" below it,
followed by a 16-colour CLUT block. The cursor reads characters from the Shift-JIS
grid in the exe (make_patch.name_grid_sjis), so this picture has to show the same rows:
the English rows on top, then the original rows moved down.

usage: namegrid.py <F0073.BIN in> <F0073.BIN out> [preview.png]
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import enfont  # noqa: E402
import rle  # noqa: E402

CELL = 12
COLS, ROWS = 13, 16
INK, SHADOW = 1, 2


def unpack(src):
    w, h, px, used = rle.decode(src, 0)
    a = np.frombuffer(px, np.uint8).reshape(h, w * 2)
    img = np.zeros((h, w * 4), np.uint8)
    img[:, 0::2] = a & 15
    img[:, 1::2] = a >> 4
    return img, w, h, used


def pack(img):
    return (img[:, 0::2] | (img[:, 1::2] << 4)).astype(np.uint8)


def draw_char(img, ch, cx, cy):
    rows = enfont.glyph_rows(ch)
    w = len(rows[0])
    x0 = cx + (CELL - 1 - w) // 2
    for gy, row in enumerate(rows):
        y = cy + gy - 1
        for dx, c in enumerate(row):
            if c == '#':
                for sx, sy, v in ((1, 1, SHADOW), (0, 0, INK)):
                    yy, xx = y + sy, x0 + dx + sx
                    if 0 <= yy < cy + CELL and xx < cx + CELL and (v == INK or img[yy, xx] != INK):
                        img[yy, xx] = v


def build(src, eng_rows):
    img, w, h, used = unpack(src)
    assert (w, h) == (39, 208), (w, h)
    grid = img[:ROWS * CELL].copy()
    n = len(eng_rows)
    new = np.zeros_like(grid)
    new[n * CELL:] = grid[:(ROWS - n) * CELL]           # original rows moved down
    for r, text in enumerate(eng_rows):
        for c, ch in enumerate(text.ljust(COLS)[:COLS]):
            if ch != ' ':
                draw_char(new, ch, c * CELL, r * CELL)
    img[:ROWS * CELL] = new
    # Same block size as the original, so the CLUT block stays where it was and the file
    # is laid out exactly like the Japanese one (the native build's disc timing at this
    # screen depended on it).
    blk = rle.encode_exact(w, h, pack(img).tobytes(), used)
    out = bytearray(src)
    out[:len(blk)] = blk
    return bytes(out), img


def main():
    import make_patch
    src = open(sys.argv[1], 'rb').read()
    data, img = build(src, make_patch.NAME_ROWS)
    open(sys.argv[2], 'wb').write(data)
    if len(sys.argv) > 3:
        from PIL import Image
        pal = np.array([(0, 0, 90), (255, 255, 255), (50, 50, 50), (140, 0, 0), (80, 255, 255),
                        (255, 0, 0)] + [(0, 0, 0)] * 10, np.uint8)
        Image.fromarray(pal[img]).resize((156 * 4, 208 * 4), Image.NEAREST).save(sys.argv[3])


if __name__ == '__main__':
    main()
