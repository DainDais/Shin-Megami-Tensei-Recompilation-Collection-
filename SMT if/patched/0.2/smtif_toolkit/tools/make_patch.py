#!/usr/bin/env python3
"""Build the English patch: translated text blocks + English tiles in the font + engine tweaks.

Usage: make_patch.py <original.bin> <out.bin>

Each entry in SPECS names a compressed string table (file, block offset, end of its slot)
and a translation JSON (id -> English). Untranslated strings keep their original codes.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import enfont  # noqa: E402
import en_insert as E  # noqa: E402
from build import Builder  # noqa: E402
from font import load_font, set_glyph, build_f0013  # noqa: E402
from lz import pack_block, decompress, compress  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
WIDTH_TABLE = 0xe3680              # exe offset of dialogue width table (RAM 0x800F2E80)
GAP_PATCHES = [0x3a930, 0x4bb9c]   # 'addiu v1, s4/s6, 1' -> 0 : 1px letter spacing
TILE_BUDGET = 700
MENU_W = 135                       # max pixels for a menu choice

SPECS = [
    # file, block offset, slot end, translation, kind
    ('D/F0016.BIN', 0x12cc, 0x2000, 'F0016_b3.json', 'dialogue'),
    # Menu choices (F0017) use a separate menu font (likely F0003) -- not patched yet:
    # ('D/F0017.BIN', 0x0000, 0x1000, 'F0017_b0.json', 'menu'),
]


def read_table(data, off):
    m, csz, usz = struct.unpack_from('<III', data, off)
    out, _ = decompress(data, off + 12, usz)
    n = struct.unpack_from('<I', out, 0)[0] // 4
    offs = struct.unpack_from(f'<{n}I', out, 0)
    strings = []
    for o in offs:
        codes = []
        p = o
        while True:
            c = struct.unpack_from('<H', out, p)[0]
            if c == 0xffff:
                break
            codes.append(c)
            p += 2
        strings.append(codes)
    return strings


def main():
    orig, outp = sys.argv[1], sys.argv[2]
    files = {}
    jobs = []
    for path, off, end, tname, kind in SPECS:
        if path not in files:
            files[path] = bytearray(open(os.path.join(ROOT, 'disc', path), 'rb').read())
        strings = read_table(files[path], off)
        tr = json.load(open(os.path.join(ROOT, 'trans', tname), encoding='utf-8'))
        toks = {}
        for k, v in tr.items():
            if k.startswith('_'):
                continue
            t = E.parse(v)
            if kind == 'dialogue':
                t = E.wrap(t)
                lines, w = E.page_stats(t)
                if lines > 3 or w > E.LINE_W:
                    print(f'  WARN {tname}:{k}: {lines} lines/page, {w}px')
            else:
                w = sum(E.tok_width(x) for x in t)
                if w > MENU_W:
                    print(f'  WARN {tname}:{k}: menu text {w}px > {MENU_W}')
            toks[int(k)] = t
        jobs.append((path, off, end, tname, strings, toks))

    corpus = [r for j in jobs for t in j[5].values() for r in E.runs(t) if isinstance(r, str)]
    tiles = E.build_tiles(corpus, TILE_BUDGET)
    slots = E.slot_order()
    tilecodes = {t: slots[k] for k, t in enumerate(tiles)}
    print(f'tiles: {len(tiles)} (reusing kanji slots used <= '
          f'{max(json.load(open(os.path.join(ROOT, "tools", "glyph_usage.json")))[f"{slots[k]:04x}"] for k in range(len(tiles)))}x)')

    for path, off, end, tname, strings, toks in jobs:
        codes = [list(s) for s in strings]
        for i, t in toks.items():
            codes[i] = E.encode_string(t, tilecodes)
        order = E.best_order(codes, compress)
        blk = pack_block(E.pack_table_ordered(codes, order))
        room = end - off
        print(f'{tname}: {len(toks)} lines translated, packed {len(blk)} / room {room}')
        if len(blk) > room:
            raise SystemExit(f'{tname} DOES NOT FIT')
        files[path][off:end] = blk + bytes(room - len(blk))

    b = Builder(orig, outp)
    for path, data in files.items():
        b.replace(path, bytes(data))
    f13 = open(os.path.join(ROOT, 'disc', 'D', 'F0013.BIN'), 'rb').read()
    font = load_font(f13)
    for t, code in tilecodes.items():
        px, W = enfont.render_tile(t)
        set_glyph(font, code, px)
        b.patch('SLPM_871.53', WIDTH_TABLE + code, bytes([max(1, W)]))
    b.replace('D/F0013.BIN', build_f0013(font, f13))
    exe = b.get('SLPM_871.53')
    for off in GAP_PATCHES:
        assert exe[off:off + 2] == b'\x01\x00', exe[off:off + 4].hex()
        b.patch('SLPM_871.53', off, b'\x00\x00')
    b.finish()
    json.dump(tilecodes, open(os.path.join(ROOT, 'trans', 'tiles.json'), 'w'), ensure_ascii=False, indent=0)


if __name__ == '__main__':
    main()
