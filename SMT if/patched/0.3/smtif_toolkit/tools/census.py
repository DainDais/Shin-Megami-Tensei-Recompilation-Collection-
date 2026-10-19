#!/usr/bin/env python3
"""Glyph census: how often each glyph code is used by every piece of text on the disc.

Used to pick which kanji slots the English tiles may take over: a slot is safe when the
text still left in Japanese no longer needs it.

usage: census.py            -> writes tools/glyph_census.json  {source_id: {code_hex: count}}
"""
import glob
import json
import os
import struct
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import textsrc as T  # noqa: E402
from lz import decompress  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SKIP = {'F0084.BIN', 'F0040.BIN', 'F0092.BIN'}        # unused copies / debug-only text
OVERLAYS = {'F0049.BIN', 'F0088.BIN'}                # code overlays with inline strings
TEXT_MAX = 0x55B


def tables_in_file(data):
    """Yield (block_offset, codes_list) for every block holding a string table."""
    pos = 0
    while pos + 12 <= len(data):
        magic, size = struct.unpack_from('<II', data, pos)
        lo = magic & 0xFFFF
        payload = None
        if lo == 0x0201 and 12 < size <= len(data) - pos:
            usize = struct.unpack_from('<I', data, pos + 8)[0]
            if 0 < usize < 0x200000:
                try:
                    payload, end = decompress(data, pos + 12, usize)
                    if end - pos != size:
                        payload = None
                except Exception:
                    payload = None
        elif lo == 0x0001 and 16 < size <= len(data) - pos:
            payload = bytes(data[pos + 8:pos + size])
        if payload is not None:
            t = T.parse_table(payload)
            if t:
                yield pos, t
        pos += 4


def overlay_strings(data):
    """Heuristic: FFFF-terminated runs of >= 2 text glyphs (kana/kanji) in a code overlay."""
    n = len(data) // 2
    a = struct.unpack(f'<{n}H', data[:n * 2])
    cur = []
    for v in a:
        if v == 0xFFFF:
            if len(cur) >= 2 and sum(1 for c in cur if c <= TEXT_MAX) >= 2:
                yield cur
            cur = []
        elif v <= TEXT_MAX or v >= 0xFF00:
            cur.append(v)
        else:
            cur = []


def build():
    out = {}
    exe = open(os.path.join(T.DISC, 'SLPM_871.53'), 'rb').read()
    for k, (off, payload) in enumerate(T.exe_tables(exe)):
        cnt = Counter(c for s in T.parse_table(payload) for c in s if c <= TEXT_MAX)
        out[f'EXE_t{k}'] = cnt
    for p in sorted(glob.glob(os.path.join(T.DISC, 'D', 'F*'))):
        name = os.path.basename(p)
        if name in SKIP:
            continue
        data = open(p, 'rb').read()
        if len(data) > 9_000_000:
            continue
        for off, t in tables_in_file(data):
            out[f'{name[:-4]}@{off:x}'] = Counter(c for s in t for c in s if c <= TEXT_MAX)
        if name in OVERLAYS:
            out[f'{name[:-4]}@code'] = Counter(c for s in overlay_strings(data) for c in s if c <= TEXT_MAX)
    return {k: {f'{c:04x}': n for c, n in v.items()} for k, v in out.items() if v}


if __name__ == '__main__':
    c = build()
    json.dump(c, open(os.path.join(HERE, 'glyph_census.json'), 'w'), indent=0, sort_keys=True)
    tot = Counter()
    for v in c.values():
        tot.update({k: n for k, n in v.items()})
    print(f'{len(c)} sources, {sum(tot.values())} glyphs, {len(tot)} distinct')
