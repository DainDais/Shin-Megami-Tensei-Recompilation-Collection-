#!/usr/bin/env python3
"""Find uncompressed string-table blocks (magic 1) in the disc files.

Block: u32 1, u32 size (incl. 8-byte header), then the same table as an LZ text
block: u32 offsets[n] (relative to header end, offsets[0] == 4*n), FFFF-terminated
LE16 glyph strings.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smtext import decode_units  # noqa: E402


def parse_table(b, base, size):
    if size < 8:
        return None
    first = struct.unpack_from('<I', b, base)[0]
    if first == 0 or first % 4 or first >= size:
        return None
    n = first // 4
    offs = struct.unpack_from(f'<{n}I', b, base)
    if any(o % 2 or o >= size or o < first for o in offs):
        return None
    out = []
    for o in offs:
        e = base + o
        while e + 1 < base + size and struct.unpack_from('<H', b, e)[0] != 0xFFFF:
            e += 2
        if e + 1 >= base + size:
            return None
        out.append((o, e + 2 - base))
    return out


def find_raw_blocks(b):
    """Yield (offset, size, strings[(start,end) rel. to offset+8])."""
    pos = 0
    while pos + 16 <= len(b):
        m, size = struct.unpack_from('<II', b, pos)
        if m == 1 and 16 < size <= len(b) - pos:
            t = parse_table(b, pos + 8, size - 8)
            if t:
                yield pos, size, t
                pos += (size + 3) & ~3
                continue
        pos += 4


if __name__ == '__main__':
    for p in sys.argv[1:]:
        b = open(p, 'rb').read()
        for off, size, t in find_raw_blocks(b):
            s0 = decode_units(b, off + 8 + t[0][0], off + 8 + t[0][1] - 2)
            s1 = decode_units(b, off + 8 + t[-1][0], off + 8 + t[-1][1] - 2)
            print(f'{os.path.basename(p)} @{off:#x} size {size:#x} n={len(t)}  first={s0[:30]!r} last={s1[:30]!r}')
