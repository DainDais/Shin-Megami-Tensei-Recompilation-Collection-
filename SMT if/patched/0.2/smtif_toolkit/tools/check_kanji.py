#!/usr/bin/env python3
"""Validate transcribed kanji sheets: count, JIS ordering. Writes tools/kanji_table.tsv."""
import glob, os
START = 0x109
chars = []
for fn in sorted(glob.glob(os.path.join(os.path.dirname(__file__), 'kanji', 's*.txt'))):
    s = open(fn, encoding='utf-8').read().strip()
    print(os.path.basename(fn), len(s))
    chars += list(s)
prev = 0
bad = 0
rows = []
for i, c in enumerate(chars):
    g = START + i
    try:
        code = int.from_bytes(c.encode('shift_jis'), 'big')
    except UnicodeEncodeError:
        code = -1
    flag = ''
    if code <= prev:
        flag = '  <-- ORDER'
        bad += 1
    if code > 0:
        prev = code
    rows.append((g, c, code))
    if flag:
        print(f'{g:04x} {c} {code:04x}{flag} (prev {chars[i-1]})')
with open(os.path.join(os.path.dirname(__file__), 'kanji_table.tsv'), 'w', encoding='utf-8') as f:
    for g, c, code in rows:
        f.write(f'{g:04x}\t{c}\n')
print('total', len(chars), 'order problems', bad, 'next glyph', hex(START + len(chars)))
