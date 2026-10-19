"""Shared helpers: glyph table, decode, LZ block discovery."""
import os, struct
from lz import decompress

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = [l.rstrip('\n').split('\t')[1] for l in open(os.path.join(HERE, 'table.tsv'), encoding='utf-8')]
REV = {c: i for i, c in enumerate(TABLE)}


def decode_units(b, start=0, end=None):
    """Decode LE16 glyph stream to text with {xxxx} for control/unknown codes."""
    end = len(b) if end is None else end
    out = []
    for i in range(start, end - 1, 2):
        v = b[i] | b[i + 1] << 8
        if v < len(TABLE):
            out.append(TABLE[v])
        else:
            out.append('{%04x}' % v)
    return ''.join(out)


def find_lz_blocks(data):
    """Yield (offset, csize, usize, payload) for every valid 0x201 LZ block."""
    pos = 0
    while True:
        i = data.find(b'\x01\x02\x00\x00', pos)
        if i < 0:
            return
        pos = i + 1
        if i % 2:
            continue
        csz, usz = struct.unpack_from('<II', data, i + 4)
        if not (12 < csz <= len(data) - i and 0 < usz < 0x200000 and usz >= csz // 3):
            continue
        try:
            out, end = decompress(data, i + 12, usz)
        except Exception:
            continue
        if end - i != csz:
            continue
        yield i, csz, usz, out
        pos = i + csz
