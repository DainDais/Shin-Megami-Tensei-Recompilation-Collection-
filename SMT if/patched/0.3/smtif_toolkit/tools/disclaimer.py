#!/usr/bin/env python3
"""English fiction disclaimer for D/F0083.BIN (shown before the attract movie).

F0083 = RLE 0x102 image, 160 halfwords x 240 = 320x240 at 8 bpp, then a 256-entry
CLUT block. Indices 1..30 are a white-to-dark gray ramp, 31 is transparent black.
The new image must not be larger than the original so the CLUT stays where it is.

usage: disclaimer.py <F0083.BIN in> <F0083.BIN out> [preview.png]
"""
import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
import rle  # noqa: E402

LINES = [
    "This game is a work of fiction.",
    "Its characters and groups have no connection",
    "to any real persons or organizations.",
]
FONT = '/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf'
SIZE = 15
TOPS = [87, 115, 143]      # same rows as the Japanese lines


def render():
    img = Image.new('L', (320, 240), 0)
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, SIZE)
    for text, y in zip(LINES, TOPS):
        w = d.textlength(text, font=f)
        d.text(((320 - w) / 2, y), text, font=f, fill=255)
    return np.asarray(img, dtype=np.float32)


def indices():
    lum = render()
    # 0 -> 31 (clear); full ink -> 7, the brightest level the Japanese text mostly uses
    return 31 - np.rint(lum / 255.0 * 24).astype(np.uint8)


def build(src):
    """Original F0083.BIN bytes -> English F0083.BIN bytes (same file size).

    The RLE decoder is driven by the block size in the header, and the loader finds the
    CLUT block right after the image block (4-byte aligned). So the new, smaller image
    block gets its own size and the CLUT block is moved up behind it."""
    w, h, px, used = rle.decode(src, 0)
    assert (w, h) == (160, 240)
    # exactly the original block size: the CLUT block and the rest of the file stay put
    blk = rle.encode_exact(160, 240, indices().tobytes(), used)
    out = bytearray(src)
    out[:len(blk)] = blk
    return bytes(out)


def main():
    src = open(sys.argv[1], 'rb').read()
    open(sys.argv[2], 'wb').write(build(src))
    idx = indices()
    if len(sys.argv) > 3:
        Image.fromarray(((31 - idx.clip(1, 31).astype(np.int32)) * 255 // 30).astype(np.uint8)).save(sys.argv[3])


if __name__ == '__main__':
    main()
