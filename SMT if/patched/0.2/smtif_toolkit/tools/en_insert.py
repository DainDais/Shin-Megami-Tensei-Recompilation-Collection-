#!/usr/bin/env python3
"""English text encoder for SMT if... (PS1): wrapping, multi-letter tiles, glyph assignment.

Pipeline:
  parse(str) -> tokens (chars, control codes)
  wrap by pixel width
  build tiles (pair merging, width-limited) over the whole corpus
  encode each string with the fewest tiles (DP)
"""
import json
import os
import re
import struct
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import enfont  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CTRL_RE = re.compile(r'\{([0-9a-f]{4})\}')
MAX_TILE_W = 14
NAME_W = 70          # pixels reserved for the player's name ({ff04})
LINE_W = 262         # max pixels per line (measured from the original text, see measure_jp)
BREAKS = {0xff01, 0xff02, 0xff03, 0xff73}


def parse(s):
    """String -> list of tokens: ('c', char) or ('k', code)."""
    out = []
    i = 0
    s = s.replace('\n', '{ff03}')
    while i < len(s):
        m = CTRL_RE.match(s, i)
        if m:
            out.append(('k', int(m.group(1), 16)))
            i = m.end()
        else:
            ch = s[i]
            if ch not in enfont.CHARSET:
                raise ValueError(f'unsupported char {ch!r} in {s!r}')
            out.append(('c', ch))
            i += 1
    return out


def tok_width(t):
    if t[0] == 'c':
        return enfont.width(t[1]) + 1
    if t[1] == 0xff04:
        return NAME_W
    return 0


def wrap(tokens, limit=LINE_W):
    """Insert {ff03} where a line exceeds the pixel limit (word-wise). Returns tokens, max lines/page."""
    out = []
    line_w = 0
    last_space = None  # index in out of last space on this line
    for t in tokens:
        if t[0] == 'k' and t[1] in BREAKS:
            out.append(t)
            line_w = 0
            last_space = None
            continue
        w = tok_width(t)
        if line_w + w > limit and last_space is not None:
            # break at last space: replace it with newline
            out[last_space] = ('k', 0xff03)
            line_w = sum(tok_width(x) for x in out[last_space + 1:])
            last_space = None
        out.append(t)
        line_w += w
        if t == ('c', ' '):
            last_space = len(out) - 1
    return out


def page_stats(tokens):
    """Max lines per page and max line width (pixels)."""
    maxl = 1
    lines = 1
    maxw = 0
    w = 0
    for t in tokens:
        if t[0] == 'k' and t[1] in (0xff03,):
            lines += 1
            maxl = max(maxl, lines)
            maxw = max(maxw, w)
            w = 0
        elif t[0] == 'k' and t[1] in (0xff02, 0xff73):
            lines = 1
            maxw = max(maxw, w)
            w = 0
        else:
            w += tok_width(t)
    return maxl, max(maxw, w)


def runs(tokens):
    """Split tokens into text runs (lists of chars) and control codes."""
    out = []
    cur = []
    for t in tokens:
        if t[0] == 'c':
            cur.append(t[1])
        else:
            if cur:
                out.append(''.join(cur))
                cur = []
            out.append(t[1])
    if cur:
        out.append(''.join(cur))
    return out


def build_tiles(texts, budget):
    """Pair-merge tile builder. texts: list of plain strings. Returns list of tile strings."""
    singles = sorted(set(''.join(texts)))
    seqs = [list(t) for t in texts]
    tiles = list(singles)
    tileset = set(tiles)
    while len(tiles) < budget:
        pairs = Counter()
        for sq in seqs:
            for a, b in zip(sq, sq[1:]):
                if enfont.tile_width(a + b) <= MAX_TILE_W:
                    pairs[a + b] += 1
        if not pairs:
            break
        best, n = pairs.most_common(1)[0]
        if n < 2:
            break
        tiles.append(best)
        tileset.add(best)
        # apply merge
        for k, sq in enumerate(seqs):
            i = 0
            ns = []
            while i < len(sq):
                if i + 1 < len(sq) and sq[i] + sq[i + 1] == best:
                    ns.append(best)
                    i += 2
                else:
                    ns.append(sq[i])
                    i += 1
            seqs[k] = ns
    return tiles


def encode_run(text, tilecodes):
    """Fewest-tiles DP over a plain string. tilecodes: {tile_string: code}."""
    n = len(text)
    maxlen = max(len(t) for t in tilecodes)
    best = [None] * (n + 1)
    best[n] = (0, None)
    for i in range(n - 1, -1, -1):
        cand = None
        for L in range(1, min(maxlen, n - i) + 1):
            t = text[i:i + L]
            if t in tilecodes and best[i + L] is not None:
                c = best[i + L][0] + 1
                if cand is None or c < cand[0]:
                    cand = (c, t)
        best[i] = cand
    out = []
    i = 0
    while i < n:
        t = best[i][1]
        out.append(tilecodes[t])
        i += len(t)
    return out


def encode_string(tokens, tilecodes):
    codes = []
    for r in runs(tokens):
        if isinstance(r, str):
            codes += encode_run(r, tilecodes)
        else:
            codes.append(r)
    return codes


def pack_table(strings_codes):
    """Build an unpacked text block: u32 offsets + LE16 strings each terminated by 0xFFFF."""
    n = len(strings_codes)
    head = 4 * n
    body = bytearray()
    offs = []
    for codes in strings_codes:
        offs.append(head + len(body))
        for c in codes:
            body += struct.pack('<H', c)
        body += b'\xff\xff'
    return struct.pack(f'<{n}I', *offs) + bytes(body)


def slot_order():
    """Glyph codes to reuse for tiles, least-used kanji first."""
    usage = json.load(open(os.path.join(HERE, 'glyph_usage.json')))
    kan = [(usage.get(f'{g:04x}', 0), g) for g in range(0x109, 0x567)]
    kan.sort()
    return [g for _, g in kan]


def pack_table_ordered(strings_codes, order):
    """Like pack_table, but lay out string bodies in `order` (offset table stays in id order).
    Identical strings share one body."""
    n = len(strings_codes)
    head = 4 * n
    body = bytearray()
    offs = [0] * n
    seen = {}
    for i in order:
        key = tuple(strings_codes[i])
        if key in seen:
            offs[i] = seen[key]
            continue
        offs[i] = head + len(body)
        seen[key] = offs[i]
        for c in strings_codes[i]:
            body += struct.pack('<H', c)
        body += b'\xff\xff'
    return struct.pack(f'<{n}I', *offs) + bytes(body)


def best_order(strings_codes, compress):
    """Greedy ordering of string bodies to maximise LZ matches (window 256)."""
    enc = [b''.join(struct.pack('<H', c) for c in cs) + b'\xff\xff' for cs in strings_codes]
    n = len(enc)
    alone = [len(compress(e)) for e in enc]

    def cost(a, b):
        tail = enc[a][-254:]
        return len(compress(tail + enc[b])) - len(compress(tail))
    order = [0]
    left = set(range(1, n))
    while left:
        a = order[-1]
        nxt = min(left, key=lambda b: (cost(a, b) - alone[b], b))
        order.append(nxt)
        left.remove(nxt)
    return order
