#!/usr/bin/env python3
"""Relative search: find byte sequences whose deltas match a word's glyph-index deltas.

Usage: relsearch.py <table.txt> <word> <file>...
Tries 8-bit and 16-bit (LE/BE) encodings. Prints file, width, offset, and value offset.
"""
import sys
import numpy as np


def search(arr, codes):
    diffs = np.diff(np.array(codes, dtype=np.int32))
    a = arr.astype(np.int32)
    L = len(a) - len(codes) + 1
    if L <= 0:
        return np.array([], dtype=np.int64)
    mask = np.ones(L, dtype=bool)
    for k, df in enumerate(diffs):
        mask &= (a[k + 1:k + 1 + L] - a[k:k + L]) == df
    return np.nonzero(mask)[0]


def main():
    tbl = open(sys.argv[1], encoding='utf-8').read()
    idx = {c: n for n, c in enumerate(tbl)}
    word = sys.argv[2]
    codes = [idx[c] for c in word]
    for fn in sys.argv[3:]:
        b = open(fn, 'rb').read()
        res = []
        res.append(('u8', np.frombuffer(b, dtype=np.uint8), 1))
        for par in (0, 1):
            seg = b[par:]
            seg = seg[:len(seg) // 2 * 2]
            res.append((f'le16+{par}', np.frombuffer(seg, dtype='<u2'), 2))
            res.append((f'be16+{par}', np.frombuffer(seg, dtype='>u2'), 2))
        for name, arr, w in res:
            hits = search(arr, codes)
            if len(hits):
                par = int(name[-1]) if '+' in name else 0
                offs = [hex(int(h) * w + par) for h in hits[:4]]
                base = int(arr[hits[0]]) - codes[0]
                print(f'{fn}\t{word}\t{name}\t{len(hits)} hits\tbase={base}\t{offs}')


if __name__ == '__main__':
    main()
