"""Font helpers: unpack/pack the 2bpp 16x12 glyph sheet (F0013) and the exe metrics table."""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lz import decompress, pack_block

GSZ = 48
METRICS_OFF = 0xe3110  # file offset of per-glyph metrics in SLPM_871.53 (RAM 0x800F2910)
NGLYPH = 0x567


def load_font(f0013_bytes):
    magic, csz, usz = struct.unpack_from('<III', f0013_bytes, 0)
    out, _ = decompress(f0013_bytes, 12, usz)
    return bytearray(out)


def get_glyph(font, i):
    b = i * GSZ
    return [[(font[b + (y * 32 + x * 2) // 8] >> ((y * 32 + x * 2) % 8)) & 3 for x in range(16)] for y in range(12)]


def set_glyph(font, i, px):
    b = i * GSZ
    for k in range(GSZ):
        font[b + k] = 0
    for y in range(12):
        for x in range(16):
            bit = y * 32 + x * 2
            font[b + bit // 8] |= (px[y][x] & 3) << (bit % 8)


def pack_font(font):
    return pack_block(bytes(font))


def build_f0013(font, orig_f0013):
    """F0013 = [font LZ block][align4][palette block (header 0x10000201)] — keep palette verbatim."""
    m, csz, usz = struct.unpack_from('<III', orig_f0013, 0)
    pal_off = csz
    pm, pcsz, pusz = struct.unpack_from('<III', orig_f0013, pal_off)
    assert pm & 0xffff == 0x201, hex(pm)
    pal = orig_f0013[pal_off:pal_off + pcsz]
    blk = bytearray(pack_font(font))
    while len(blk) % 4:
        blk.append(0)
    # header csize must point at the next block
    struct.pack_into('<I', blk, 4, len(blk))
    out = bytes(blk) + pal
    return out + bytes(len(orig_f0013) - len(out)) if len(out) < len(orig_f0013) else out
