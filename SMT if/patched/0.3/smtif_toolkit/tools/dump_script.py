#!/usr/bin/env python3
"""Dump every LZ-compressed string table on the disc to JSON.

Each 0x201 block unpacks to: u32 offsets[n] (offsets[0] == 4*n) then
0xFFFF-terminated u16 glyph strings. Output: one JSON per source file.
Usage: dump_script.py <disc_dir> <out_dir>
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smtext import decode_units, find_lz_blocks  # noqa: E402


def parse_table(out):
    if len(out) < 4:
        return None
    first = struct.unpack_from('<I', out, 0)[0]
    if first == 0 or first % 4 or first > len(out):
        return None
    n = first // 4
    offs = list(struct.unpack_from(f'<{n}I', out, 0))
    if any(o > len(out) or o % 2 for o in offs):
        return None
    strings = []
    for o in offs:
        e = o
        while e + 1 < len(out) and (out[e] | out[e + 1] << 8) != 0xFFFF:
            e += 2
        strings.append((o, e + 2))
    return strings


def main():
    disc, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    total_lines = total_units = 0
    for fn in sorted(os.listdir(os.path.join(disc, 'D'))):
        p = os.path.join(disc, 'D', fn)
        if os.path.getsize(p) > 4_000_000 or fn == 'F0013.BIN':
            continue
        data = open(p, 'rb').read()
        blocks = []
        for off, csz, usz, out in find_lz_blocks(data):
            tbl = parse_table(out)
            if tbl is None:
                blocks.append({'offset': off, 'csize': csz, 'usize': usz, 'kind': 'raw'})
                continue
            lines = []
            for i, (s, e) in enumerate(tbl):
                txt = decode_units(out, s, e - 2)
                lines.append({'id': i, 'ja': txt, 'en': ''})
                total_units += (e - s) // 2
            total_lines += len(lines)
            blocks.append({'offset': off, 'csize': csz, 'usize': usz, 'kind': 'text', 'lines': lines})
        if any(b['kind'] == 'text' for b in blocks):
            with open(os.path.join(outdir, fn.replace('.BIN', '.json')), 'w', encoding='utf-8') as f:
                json.dump({'file': fn, 'blocks': blocks}, f, ensure_ascii=False, indent=1)
            nt = sum(1 for b in blocks if b['kind'] == 'text')
            print(f'{fn}: {nt} text blocks, {sum(len(b.get("lines", [])) for b in blocks)} lines,'
                  f' {sum(1 for b in blocks if b["kind"] == "raw")} non-text blocks')
    print('TOTAL lines', total_lines, 'glyph units', total_units)


if __name__ == '__main__':
    main()
