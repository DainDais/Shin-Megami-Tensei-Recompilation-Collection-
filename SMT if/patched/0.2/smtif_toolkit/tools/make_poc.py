#!/usr/bin/env python3
"""Build the proof-of-concept English patch for the opening scene (F0016 block @0x12cc).

Usage: make_poc.py <original.bin> <out.bin> [tile_budget]
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import enfont  # noqa: E402
import en_insert as E  # noqa: E402
from build import Builder  # noqa: E402
from font import load_font, set_glyph, build_f0013, METRICS_OFF  # noqa: E402
from lz import pack_block, decompress, compress  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
WIDTH_TABLE = 0xe3680          # exe file offset of the dialogue width table (RAM 0x800F2E80)
GAP_PATCHES = [0x3a930, 0x4bb9c]  # 'addiu v1, s4/s6, 1' -> 0 : 1px letter spacing
BLOCK_OFF = 0x12cc             # text block inside F0016
BLOCK_END = 0x2000             # next event slot


def measure_jp_max_line():
    exe = open(os.path.join(ROOT, 'disc', 'SLPM_871.53'), 'rb').read()
    W = exe[WIDTH_TABLE:WIDTH_TABLE + 0x567]
    import glob
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from smtext import REV
    best = 0
    for fn in glob.glob(os.path.join(ROOT, 'script', '*.json')):
        for b in json.load(open(fn, encoding='utf-8'))['blocks']:
            for l in b.get('lines', []):
                for page in l['ja'].replace('{ff02}', '{ff03}').split('{ff03}'):
                    w = 0
                    i = 0
                    while i < len(page):
                        if page[i] == '{':
                            i = page.index('}', i) + 1
                            continue
                        w += (W[REV[page[i]]] or 14) + 2
                        i += 1
                    best = max(best, w)
    return best


def main():
    orig, out = sys.argv[1], sys.argv[2]
    budget = int(sys.argv[3]) if len(sys.argv) > 3 else 450
    print('original longest dialogue line: %d px' % measure_jp_max_line())

    tr = json.load(open(os.path.join(ROOT, 'trans', 'F0016_b3.json'), encoding='utf-8'))
    ids = sorted(int(k) for k in tr if not k.startswith('_'))
    toks = {}
    for i in ids:
        t = E.wrap(E.parse(tr[str(i)]))
        lines, w = E.page_stats(t)
        if lines > 3 or w > E.LINE_W:
            print(f'  WARN line {i}: {lines} lines/page, {w}px')
        toks[i] = t

    corpus = [r for i in ids for r in E.runs(toks[i]) if isinstance(r, str)]
    tiles = E.build_tiles(corpus, budget)
    slots = E.slot_order()
    assert len(tiles) <= len(slots)
    tilecodes = {t: slots[k] for k, t in enumerate(tiles)}
    print(f'tiles: {len(tiles)} ({sum(1 for t in tiles if len(t) == 1)} single, '
          f'{sum(1 for t in tiles if len(t) > 1)} multi)')

    codes = [E.encode_string(toks[i], tilecodes) for i in ids]
    nchars = sum(len(r) for r in corpus)
    ntiles = sum(1 for cs in codes for c in cs if c < 0xff00)
    print(f'english chars {nchars} -> {ntiles} glyph codes ({nchars / ntiles:.2f} chars/code)')

    order = E.best_order(codes, compress)
    raw = E.pack_table_ordered(codes, order)
    blk = bytearray(pack_block(raw))
    avail = BLOCK_END - BLOCK_OFF
    print(f'text block: unpacked {len(raw)} bytes, packed {len(blk)} bytes, room {avail} bytes')
    if len(blk) > avail:
        raise SystemExit('DOES NOT FIT')

    # --- assemble disc
    b = Builder(orig, out)
    f16 = bytearray(open(os.path.join(ROOT, 'disc', 'D', 'F0016.BIN'), 'rb').read())
    f16[BLOCK_OFF:BLOCK_END] = bytes(blk) + bytes(avail - len(blk))
    b.replace('D/F0016.BIN', bytes(f16))

    f13 = open(os.path.join(ROOT, 'disc', 'D', 'F0013.BIN'), 'rb').read()
    font = load_font(f13)
    for t, code in tilecodes.items():
        px, W = enfont.render_tile(t)
        set_glyph(font, code, px)
        b.patch('SLPM_871.53', WIDTH_TABLE + code, bytes([max(1, W)]))
    b.replace('D/F0013.BIN', build_f0013(font, f13))
    for off in GAP_PATCHES:
        exe = b.get('SLPM_871.53')
        assert exe[off:off + 2] == b'\x01\x00', exe[off:off + 4].hex()
        b.patch('SLPM_871.53', off, b'\x00\x00')
    b.finish()
    json.dump({t: c for t, c in tilecodes.items()}, open(os.path.join(ROOT, 'trans', 'tiles_poc.json'), 'w'),
              ensure_ascii=False, indent=0)


if __name__ == '__main__':
    main()
