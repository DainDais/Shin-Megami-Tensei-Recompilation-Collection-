#!/usr/bin/env python3
"""Build the English patch (v0.3).

Usage: make_patch.py <original.bin> <out.bin> [--budget N]

Text sources (translations live in trans/, keyed by string number):
  F0016_u<unit>_b<block>.json   event scripts (F0016 is repacked, scene index rewritten,
                                file moved into ZZZ.BIN when it grows)
  F0018_o<offset>.json          map events, each text block grows up to the next block
  F0017_b0/b1/b2.json           menus / ally farewells / party-full prompts (fixed slots)
  F0094_b0..b6.json             partner, demon, item, item-description, spell,
                                spell-description and race names (block chain, heap-loaded)
  F0075_b0.json                 battle messages      (raw block, stored as LZ)
  F0076_o01814/o02a1c/o02c7c    demon-conversation narration, results and answer choices
  F0043_b0.json                 Cathedral of Shadows (raw block, stored as LZ)
  EXE_t0..t5.json               the six message tables inside the executable
Graphics: D/F0083.BIN (fiction disclaimer) is redrawn; the attract movie is patched
separately by tools/fmv_patch.py.
Name entry: the Shift-JIS grid in the executable gets Latin letters, and the SJIS->glyph
tables map full-width letters/digits to the single-letter English glyphs.
"""
import glob
import json
import os
import re
import struct
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import enfont  # noqa: E402
import en_insert as E  # noqa: E402
import f16pack  # noqa: E402
import textsrc as T  # noqa: E402
from menufont import MenuFont  # noqa: E402
from build import Builder, file_table  # noqa: E402
from cdsector import SECTOR, fix_form1  # noqa: E402
from font import load_font, set_glyph, build_f0013  # noqa: E402
from lz import pack_block, decompress, compress  # noqa: E402
from relocate import set_record, write_file_at  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
TRANS = os.path.join(ROOT, 'trans')
WIDTH_TABLE = 0xe3680              # dialogue width table (RAM 0x800F2E80)
MENU_METRICS = 0xe3110             # menu metrics table (RAM 0x800F2910): hi=trim, lo=width
GAP_PATCHES = [0x3a930, 0x4bb9c]   # dialogue 'addiu v1, s4/s6, 1' -> 0 : 1px letter spacing
TILE_BUDGET = 800
MENU_W = 135
MENU_MAX_CODES = 11               # longer menu strings overflow and hang the game
FILEPOS_LBA = 23
F0016_INDEX = 16                   # entry in FILEPOS.DAT

# runtime-inserted fields: width reserved when wrapping
E.FIELD_W.update({0xff67: 48, 0xff68: 48, 0xff19: 96, 0xff76: 40, 0xff7b: 96,
                  0xff77: 96, 0xff7d: 96, 0xff7a: 120, 0xff05: 96})

# kind -> (wrap width or None, max lines per page or None, max codes or None, max width or None)
KINDS = {
    'dialogue': (E.LINE_W, 3, None, None),
    'msg':      (250, 3, None, None),
    'card':     (250, 6, None, None),
    'help':     (None, 1, None, 250),
    'menu':     (None, 1, MENU_MAX_CODES, MENU_W),
    'desc':     (128, 5, None, None),
    'resist':   (150, 2, None, None),
    'shop':     (E.LINE_W, 4, None, None),
    'title':    (228, 4, None, None),
}

# chain files: file -> {block index: (translation, kind[, name-width])}
CHAINS = {
    'D/F0094.BIN': {0: ('F0094_b0.json', 'name:96'), 1: ('F0094_b1.json', 'name:96'),
                    2: ('F0094_b2.json', 'name:120'), 3: ('F0094_b3.json', 'desc'),
                    4: ('F0094_b4.json', 'name:96'), 5: ('F0094_b5.json', 'desc'),
                    6: ('F0094_b6.json', 'name:48')},
    'D/F0075.BIN': {0: ('F0075_b0.json', 'dialogue')},
    'D/F0076.BIN': {2: ('F0076_o01814.json', 'dialogue'), 3: ('F0076_o02a1c.json', 'dialogue'),
                    4: ('F0076_o02c7c.json', 'menu')},
    'D/F0043.BIN': {0: ('F0043_b0.json', 'dialogue')},
}
# fixed slots: (file, block offset, slot end, translation, kind)
SLOTS = [
    ('D/F0017.BIN', 0x0000, 0x1000, 'F0017_b0.json', 'menu'),
    ('D/F0017.BIN', 0x1000, 0x1800, 'F0017_b1.json', 'dialogue'),
    ('D/F0017.BIN', 0x1800, 0x2000, 'F0017_b2.json', 'dialogue'),
]
# string tables inside code overlays, rewritten in place: (file, table offset, room end, translation, kind)
OVERLAY_TABLES = [
    ('D/F0049.BIN', 0x798C, 0x9B70, 'F0049_t798c.json', 'shop'),     # shops, healers, MAG dealer
    ('D/F0088.BIN', 0x42B4, 0x45D8, 'F0088_t42b4.json', 'title'),    # title-screen memory card prompts
]
SLOT_FILES = ['F0018']            # map events: blocks grow up to the next block
EXE_KINDS = ['msg', 'label', 'card', 'resist', 'msg', 'msg']
# help-bar strings (one line, no {ff03}) inside otherwise multi-line tables
HELP_IDS = {('EXE_t0.json', i) for i in range(0, 28)} | {('F0075_b0.json', i) for i in range(273, 299)}

NAME_GRID = 0x15014               # Shift-JIS name-entry grid in the exe (13 x rows)
SJIS_LEAD = {0x81: (0x800F33F0, 0x41), 0x82: (0x800F3558, 0x4F)}   # lead byte -> (u16 table, first trail)
FORCED_SINGLES = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-.\'!?&'
NAME_ROWS = ['ABCDEFGHIJKLM', 'NOPQRSTUVWXYZ', 'abcdefghijklm', 'nopqrstuvwxyz', '0123456789-.\'',
             '!?&          ']     # English keyboard rows (exe grid + F0073 picture)


def slot_jobs():
    jobs = list(SLOTS)
    for name in SLOT_FILES:
        d = json.load(open(os.path.join(ROOT, 'script', f'{name}.json'), encoding='utf-8'))
        size = os.path.getsize(os.path.join(ROOT, 'disc', 'D', f'{name}.BIN'))
        offs = [b['offset'] for b in d['blocks']] + [size]
        for k, b in enumerate(d['blocks']):
            t = f"{name}_o{b['offset']:05x}.json"
            if os.path.exists(os.path.join(TRANS, t)):
                jobs.append((f'D/{name}.BIN', b['offset'], offs[k + 1], t, 'dialogue'))
    return jobs


def read_lz_table(data, off):
    m, csz, usz = struct.unpack_from('<III', data, off)
    out, _ = decompress(data, off + 12, usz)
    return f16pack.parse_table(out)


class Job:
    """One string table to translate: Japanese codes, English tokens per id, kind."""

    def __init__(self, name, ja, tname, kind):
        self.name, self.ja, self.tname, self.kind = name, ja, tname, kind
        self.tr = {}
        raw = json.load(open(os.path.join(TRANS, tname), encoding='utf-8'))
        for k, v in raw.items():
            if k.startswith('_'):
                continue
            i = int(k)
            if i >= len(ja):
                raise SystemExit(f'{tname}: id {i} out of range ({len(ja)} strings)')
            self.tr[i] = E.parse(v)
        self.codes = None

    def kind_of(self, i):
        if (self.tname, i) in HELP_IDS:
            return 'help'
        return self.kind

    def prepare(self):
        """Wrap tokens according to kind (before tiles are known)."""
        for i, t in list(self.tr.items()):
            k = self.kind_of(i)
            if k in KINDS and KINDS[k][0]:
                self.tr[i] = E.wrap(t, KINDS[k][0])

    def check(self, tilecodes, errors):
        self.codes = [list(s) for s in self.ja]
        jmax = max((len([c for c in s if c < 0xff00]) for s in self.ja), default=0)
        for i, t in self.tr.items():
            if (self.tname, i) in HUD_SEG:
                codes = [tilecodes[p] for p in HUD_SEG[(self.tname, i)]]
            else:
                codes = E.encode_string(t, tilecodes)
            self.codes[i] = codes
            k = self.kind_of(i)
            ncodes = len([c for c in codes if c < 0xff00])
            if k == 'label':
                # status/equip labels: must fit the Japanese label's pixel width (12 px per glyph)
                jw = 12 * len([c for c in self.ja[i] if c < 0xff00])
                w = sum(E.tok_width(x) for x in t if not (x[0] == 'k'))
                if w > jw:
                    errors.append(f'{self.tname}:{i}: label {w}px > {jw}px')
                continue
            if k.startswith('name'):
                limit = int(k.split(':')[1])
                w = sum(E.tok_width(x) for x in t)
                if w > limit:
                    print(f'  WARN {self.tname}:{i}: name {w}px > {limit}px')
                # names are copied into fixed buffers sized for the longest Japanese name
                if ncodes > jmax:
                    errors.append(f'{self.tname}:{i}: name needs {ncodes} glyphs > {jmax} (longest Japanese)')
                continue
            wrapw, maxl, maxc, maxw = KINDS[k]
            lines, w = E.page_stats(t)
            if maxc and ncodes > maxc:
                errors.append(f'{self.tname}:{i}: {k} string needs {ncodes} glyphs > {maxc}')
            if maxw and w > maxw:
                (errors.append if k == 'menu' else print)(f'  WARN {self.tname}:{i}: {k} text {w}px > {maxw}px')
            if maxl and lines > maxl:
                print(f'  WARN {self.tname}:{i}: {lines} lines/page > {maxl}')
            if wrapw and w > wrapw:
                print(f'  WARN {self.tname}:{i}: line {w}px > {wrapw}px')

    def over_limit(self, tilecodes):
        """Ids whose encoding exceeds a hard glyph-count limit (names, menus)."""
        out = []
        jmax = max((len([c for c in s if c < 0xff00]) for s in self.ja), default=0)
        for i, t in self.tr.items():
            k = self.kind_of(i)
            limit = jmax if k.startswith('name') else KINDS.get(k, (None, None, None, None))[2]
            if limit and len([c for c in E.encode_string(t, tilecodes) if c < 0xff00]) > limit:
                out.append(i)
        return out

    def gone(self):
        c = Counter()
        for i in self.tr:
            c.update(self.ja[i])
        return c


# ---------------------------------------------------------------- HUD names
# The party panel (and a few other spots) draw names in a small Shift-JIS font: the game turns
# the name's glyph codes back into Shift-JIS with the function at 0x8004AE8C. Originally every
# glyph from 0x109 up became '・'. That function is rewritten (G2S_CODE) to expand the tiles used
# by names into their letters, as upper-case full-width Shift-JIS (the small font has no lower
# case). Name tiles get one contiguous range of codes so a flat table of 4 letters per code
# (HUD cells) describes them.
HUD_NAME_FILES = ('F0094_b0.json', 'F0094_b1.json')    # partner names, demon names
HUD_SEG = {}                                              # (file, id) -> list of tile strings
HUD_MAX_CHARS = 8                                         # sprites per name the panel can take (as in Japanese)
HUD_WINDOW = 340                                          # codes covered by the HUD cell table (4 bytes each)
G2S_FUNC = (0x8004AE8C, 0x8004AF78)
KANA_SJIS = 0x800F3764                                    # original glyph -> SJIS table (0x109 entries)
SJIS81 = {' ': 0x40, ',': 0x43, '.': 0x44, ':': 0x46, ';': 0x47, '?': 0x48, '!': 0x49, '/': 0x5E,
          '~': 0x60, "'": 0x66, '"': 0x68, '(': 0x69, ')': 0x6A, '+': 0x7B, '&': 0x7B, '-': 0x7C}


def hud_byte(ch):
    """One letter -> HUD cell byte: >= 0x40 is the trail byte after 0x82, 1..0x3F is 0x81, b + 0x3F."""
    if 'A' <= ch <= 'Z' or 'a' <= ch <= 'z':
        return 0x60 + ord(ch.upper()) - ord('A')
    if '0' <= ch <= '9':
        return 0x4F + ord(ch) - ord('0')
    return SJIS81.get(ch, 0x45) - 0x3F                    # unknown -> '・'


def hud_segments(jobs, tiles):
    """Split every partner/demon name into tiles of at most 4 letters, within the glyph limit,
    re-using as few distinct tiles as possible. -> (sorted name tiles, {(file, id): pieces})."""
    tileset = {t for t in tiles if len(t) <= 4}
    chosen = set(c for c in FORCED_SINGLES + ' ' if c in tileset)
    items = []
    for j in jobs:
        jmax = max(len([c for c in s if c < 0xff00]) for s in j.ja)
        for i, toks in j.tr.items():
            if any(k == 'k' for k, _ in toks):
                raise SystemExit(f'{j.tname}:{i}: control code in a name')
            items.append((j.tname, i, ''.join(ch for _, ch in toks), jmax))
    items.sort(key=lambda x: (-len(x[2]) / x[3], x[2]))
    seg = {}
    for tname, i, text, jmax in items:
        n = len(text)
        memo = {}

        def best(pos, left):
            if pos == n:
                return (0, 0, ())
            if left == 0:
                return None
            key = (pos, left)
            if key in memo:
                return memo[key]
            cand = None
            for L in range(1, min(4, n - pos) + 1):
                t = text[pos:pos + L]
                if t not in tileset:
                    continue
                rest = best(pos + L, left - 1)
                if rest is None:
                    continue
                c = (rest[0] + (t not in chosen), rest[1] + 1, (t,) + rest[2])
                if cand is None or c[:2] < cand[:2]:
                    cand = c
            memo[key] = cand
            return cand
        r = best(0, jmax)
        if r is None:
            raise SystemExit(f'{tname}:{i}: {text!r} does not fit {jmax} HUD tiles')
        chosen |= set(r[2])
        seg[(tname, i)] = list(r[2])
    return sorted(chosen, key=lambda t: (len(t), t)), seg


def mips(op, rs=0, rt=0, imm=0):
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def g2s_code(func, cells, base, count):
    """MIPS for glyph string (a0) -> Shift-JIS (a1); returns the number of characters.
    FFFE -> '~~'; other control codes skipped; kana via the original table; name tiles expand
    to up to four letters from `cells`; other kanji -> '・'. Stops after HUD_MAX_CHARS."""
    V0, A0, A1, A2, A3, T0, T1, T2, T3, T4, T5, T6, T7, RA = 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 31
    ADDIU, SLTIU, ORI, LUI, LBU, LHU, SB, BEQ, BNE = 9, 11, 13, 15, 36, 37, 40, 4, 5
    def hi(x): return ((x + 0x8000) >> 16) & 0xFFFF
    code, labels, fix = [], {}, []
    def emit(w): code.append(w)
    def br(op, rs, rt, label): fix.append((len(code), label)); emit(mips(op, rs, rt))
    def label(n): labels[n] = len(code)
    def r(funct, rd, rs=0, rt=0, sa=0): emit((rs << 21) | (rt << 16) | (rd << 11) | (sa << 6) | funct)
    def addu(rd, rs, rt): r(0x21, rd, rs, rt)
    def sll(rd, rt, sa): r(0x00, rd, 0, rt, sa)
    def srl(rd, rt, sa): r(0x02, rd, 0, rt, sa)
    NOP = 0
    r(0x25, V0, 0, 0)                                   # or v0, zero, zero   (count = 0)
    emit(mips(ORI, 0, T4, 0xFFFF))
    emit(mips(LUI, 0, T5, hi(KANA_SJIS))); emit(mips(ADDIU, T5, T5, KANA_SJIS))
    emit(mips(LUI, 0, T6, hi(cells))); emit(mips(ADDIU, T6, T6, cells))
    label('loop')
    emit(mips(SLTIU, V0, T0, HUD_MAX_CHARS))
    label('loop1')
    br(BEQ, T0, 0, 'done')
    emit(mips(LHU, A0, A2, 0))
    emit(mips(ADDIU, A0, A0, 2))
    br(BEQ, A2, T4, 'done')
    srl(A3, A2, 8)
    emit(mips(SLTIU, A3, T0, 0xFF)); br(BNE, T0, 0, 'glyph')
    emit(mips(ORI, 0, T1, 0xFFFE))
    br(BNE, A2, T1, 'loop')                             # other control codes: skip
    emit(mips(ORI, 0, T2, 0x7E))
    emit(mips(ORI, 0, T3, 0x7E))
    br(BEQ, 0, 0, 'emit2b')
    emit(mips(SB, A1, T2, 0))                           # (delay slot: first store of emit2)
    label('glyph')
    emit(mips(SLTIU, A2, T0, 0x109)); br(BEQ, T0, 0, 'tile1')
    emit(mips(ADDIU, A2, T0, -base))                    # (delay slot: first step of 'tile')
    label('kana')
    sll(T1, A2, 1)
    addu(T1, T1, T5)
    emit(mips(LBU, T1, T2, 0)); emit(mips(LBU, T1, T3, 1))
    label('emit2')
    emit(mips(SB, A1, T2, 0))
    label('emit2b')
    emit(mips(SB, A1, T3, 1))
    emit(mips(ADDIU, A1, A1, 2))
    br(BEQ, 0, 0, 'loop')
    emit(mips(ADDIU, V0, V0, 1))
    label('tile1')
    emit(mips(SLTIU, T0, T1, count)); br(BEQ, T1, 0, 'kana')
    emit(mips(ORI, 0, A2, 4))                           # (delay slot: not a name tile -> entry 4, '・')
    sll(T0, T0, 2)
    addu(T0, T0, T6)
    emit(mips(ADDIU, T0, T7, 4))
    label('cell')
    emit(mips(LBU, T0, T3, 0))
    label('cell1')
    emit(mips(ADDIU, T0, T0, 1))                        # (load delay slot)
    br(BEQ, T3, 0, 'loop')
    emit(mips(SLTIU, T3, T1, 0x40)); br(BEQ, T1, 0, 'c82')
    emit(mips(ORI, 0, T2, 0x82))
    emit(mips(ORI, 0, T2, 0x81))
    emit(mips(ADDIU, T3, T3, 0x3F))
    label('c82')
    emit(mips(SB, A1, T2, 0)); emit(mips(SB, A1, T3, 1))
    emit(mips(ADDIU, V0, V0, 1))
    emit(mips(SLTIU, V0, T1, HUD_MAX_CHARS)); br(BEQ, T1, 0, 'done')
    emit(mips(ADDIU, A1, A1, 2))                        # (delay slot)
    br(BNE, T0, T7, 'cell1')
    emit(mips(LBU, T0, T3, 0))                          # (delay slot: first load of 'cell')
    br(BEQ, 0, 0, 'loop1')
    emit(mips(SLTIU, V0, T0, HUD_MAX_CHARS))            # (delay slot: first test of 'loop')
    label('done')
    r(0x08, 0, RA)                                      # jr ra
    emit(mips(SB, A1, 0, 0))                            # sb zero, 0(a1)
    for at, name in fix:
        off = labels[name] - (at + 1)
        code[at] |= off & 0xFFFF
    n = (func[1] - func[0]) // 4
    if len(code) > n:
        raise SystemExit(f'glyph->SJIS code is {len(code)} instructions, room for {n}')
    return code + [NOP] * (n - len(code))


def name_grid_sjis(tilecodes):
    """New 13-wide name-entry grid (Shift-JIS) and SJIS->glyph table patches."""
    def fw(ch):   # half-width ASCII -> full-width SJIS bytes
        return chr(ord(ch) + 0xFEE0).encode('cp932')
    eng = NAME_ROWS
    rows = []
    for r in eng:
        b = b''
        for ch in r:
            if ch == ' ':
                b += '　'.encode('cp932')
            elif ch == "'":
                b += '’'.encode('cp932')
            elif ch == '-':
                b += '－'.encode('cp932')
            else:
                b += fw(ch)
        rows.append(b)
    # SJIS -> glyph overrides
    over = {}
    for ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.!?&':
        over[fw(ch)] = tilecodes[ch]
    over['’'.encode('cp932')] = tilecodes["'"]
    over['－'.encode('cp932')] = tilecodes['-']
    return rows, over


def main():
    orig, outp = sys.argv[1], sys.argv[2]
    budget = TILE_BUDGET
    if '--budget' in sys.argv:
        budget = int(sys.argv[sys.argv.index('--budget') + 1])
    exe = bytearray(open(os.path.join(ROOT, 'disc', 'SLPM_871.53'), 'rb').read())
    f16 = open(os.path.join(ROOT, 'disc', 'D', 'F0016.BIN'), 'rb').read()
    units, end_marker = f16pack.load(bytes(exe), f16)
    by_off = {u['off']: u for u in units}

    jobs = []
    # ---- F0016 event text
    f16_jobs = []
    for path in sorted(glob.glob(os.path.join(TRANS, 'F0016_u*_b*.json'))):
        m = re.search(r'F0016_u([0-9a-f]+)_b(\d+)\.json$', path)
        uoff, bidx = int(m.group(1), 16), int(m.group(2))
        ja = f16pack.parse_table(by_off[uoff]['blocks'][bidx]['payload'])
        j = Job(os.path.basename(path), ja, os.path.basename(path), 'dialogue')
        f16_jobs.append((uoff, bidx, j))
        jobs.append(j)
    # ---- fixed slots
    files = {}

    def get(path):
        if path not in files:
            files[path] = bytearray(open(os.path.join(ROOT, 'disc', path), 'rb').read())
        return files[path]
    slot_list = []
    for path, off, end, tname, kind in slot_jobs():
        j = Job(tname, read_lz_table(get(path), off), tname, kind)
        slot_list.append((path, off, end, j))
        jobs.append(j)
    # ---- string tables in code overlays
    ovl_list = []
    for path, off, end, tname, kind in OVERLAY_TABLES:
        j = Job(tname, T.parse_table(bytes(get(path)[off:end])), tname, kind)
        ovl_list.append((path, off, end, j))
        jobs.append(j)
    # ---- block chains
    chain_list = {}
    for path, spec in CHAINS.items():
        blocks = T.read_chain(get(path))
        chain_list[path] = (blocks, {})
        for bi, (tname, kind) in spec.items():
            ja = T.parse_table(blocks[bi]['payload'])
            j = Job(tname, ja, tname, kind)
            chain_list[path][1][bi] = j
            jobs.append(j)
    # ---- executable tables
    exe_tabs = T.exe_tables(exe)
    exe_jobs = []
    for k, (off, payload) in enumerate(exe_tabs):
        tname = f'EXE_t{k}.json'
        j = Job(tname, T.parse_table(payload), tname, EXE_KINDS[k])
        exe_jobs.append(j)
        jobs.append(j)

    for j in jobs:
        j.prepare()

    # ---- tiles over the whole corpus
    corpus = [r for j in jobs for t in j.tr.values() for r in E.runs(t) if isinstance(r, str)]
    corpus.append(FORCED_SINGLES)
    forced = []
    for attempt in range(4):
        tiles = E.build_tiles(corpus, budget, forced)
        tc = {t: k for k, t in enumerate(tiles)}       # provisional codes, only lengths matter
        over = [(j, i) for j in jobs for i in j.over_limit(tc)]
        if not over:
            break
        for j, i in over:
            for r in E.runs(j.tr[i]):
                if isinstance(r, str):
                    forced += E.chunk_tiles(r)
        print(f'  tiles: forcing {len(over)} long names/menus into fewer glyphs')
    for ch in FORCED_SINGLES:
        assert ch in tiles, ch
    census = json.load(open(os.path.join(ROOT, 'tools', 'glyph_census.json')))
    total = Counter()
    for v in census.values():
        total.update({int(k, 16): n for k, n in v.items()})
    gone = Counter()
    for j in jobs:
        gone.update(j.gone())
    rest = {f'{g:04x}': max(0, total.get(g, 0) - gone.get(g, 0)) for g in range(0x109, 0x55c)}
    # names drawn in the small HUD font: their tiles get one contiguous range of codes,
    # placed where it costs the remaining Japanese text the fewest kanji
    name_tiles, seg = hud_segments([j for j in jobs if j.tname in HUD_NAME_FILES], tiles)
    HUD_SEG.clear()
    HUD_SEG.update(seg)
    # The HUD table holds 4 bytes per code over a window of codes; inside it the name tiles take
    # the least-used kanji and the rest of the window is left alone.
    nn = len(name_tiles)
    span = min(HUD_WINDOW, 0x55c - 0x109)
    use = [rest[f'{g:04x}'] for g in range(0x109, 0x55c)]
    best_w, best_cost = None, None
    for w in range(0, len(use) - span + 1):
        cost = sum(sorted(use[w:w + span])[:nn])
        if best_cost is None or cost < best_cost:
            best_w, best_cost = w, cost
    hud_base = 0x109 + best_w
    window = sorted(range(hud_base, hud_base + span), key=lambda g: (use[g - 0x109], g))[:nn]
    tilecodes = {t: g for t, g in zip(name_tiles, sorted(window))}
    taken = set(window)
    others = [g for g in E.slot_order(rest) if g not in taken]
    for t in tiles:
        if t not in tilecodes:
            tilecodes[t] = others.pop(0)
    hud_span = span
    print(f'HUD names: {nn} tiles in {hud_base:#x}-{hud_base + span - 1:#x} (cost {best_cost} glyph uses)')
    if '--plan' in sys.argv:
        reused = [rest[f'{c:04x}'] for c in tilecodes.values()]
        raise SystemExit(f'plan: reused <= {max(reused)}x, total {sum(reused)}')
    reused = [rest[f'{c:04x}'] for c in tilecodes.values()]
    print(f'tiles: {len(tiles)}; kanji slots reused are still needed <= {max(reused)}x '
          f'(total {sum(reused)} glyph uses left in untranslated text)')

    errors = []
    for j in jobs:
        j.check(tilecodes, errors)
    if errors:
        print('\n'.join(errors))
        raise SystemExit(f'{len(errors)} errors')

    # ---- F0016
    nlines = 0
    for uoff, bidx, j in f16_jobs:
        nlines += len(j.tr)
        order = E.best_order(j.codes, compress)
        f16pack.replace_text(by_off[uoff], bidx, E.pack_table_ordered(j.codes, order))
    new16, index = f16pack.repack(units, end_marker)
    print(f'F0016: {len(f16_jobs)} text blocks, {nlines} lines; size {len(new16):#x} (was {len(f16):#x})')
    for k, v in enumerate(index):
        struct.pack_into('<I', exe, f16pack.EXE_INDEX + 4 * k, v)

    # ---- fixed slots
    for path, off, end, j in slot_list:
        order = E.best_order(j.codes, compress)
        payload = E.pack_table_ordered(j.codes, order)
        if len(payload) > f16pack.MAX_TEXT_USIZE:
            raise SystemExit(f'{j.tname}: text {len(payload)} > {f16pack.MAX_TEXT_USIZE}')
        blk = pack_block(payload)
        room = end - off
        if len(blk) > room:
            raise SystemExit(f'{j.tname}: packed {len(blk)} > room {room}')
        files[path][off:end] = blk + bytes(room - len(blk))
    print(f'slots: {len(slot_list)} tables')

    # ---- overlay tables: same place, offsets relative to the table start
    for path, off, end, j in ovl_list:
        payload = E.pack_table(j.codes)
        how = 'in order'
        if len(payload) > end - off:
            payload = E.pack_table_ordered(j.codes, E.best_order(j.codes, compress))
            how = 'shared'
        if len(payload) > end - off:
            raise SystemExit(f'{j.tname}: {len(payload)} bytes > room {end - off}')
        files[path][off:end] = payload + bytes(end - off - len(payload))
        print(f'{path}: table @{off:#x} {len(payload)} / {end - off} bytes ({how})')

    # ---- chains
    ft = file_table()
    for path, (blocks, tj) in chain_list.items():
        raws = []
        for bi, b in enumerate(blocks):
            if bi in tj:
                j = tj[bi]
                # keep the original layout rules: tables that had strings in id order with one
                # body each (F0094: its loader walks the names in order) stay that way; tables
                # that already shared/reordered bodies get the size-optimised layout
                n = struct.unpack_from('<I', b['payload'], 0)[0] // 4
                offs = struct.unpack_from(f'<{n}I', b['payload'], 0)
                if all(offs[i] < offs[i + 1] for i in range(n - 1)):
                    raws.append(T.pack_lz(b['magic'], E.pack_table(j.codes)))
                else:
                    order = E.best_order(j.codes, compress)
                    raws.append(T.pack_lz(b['magic'], E.pack_table_ordered(j.codes, order)))
            else:
                raws.append(b['raw'])
        data = T.write_chain(raws)
        orig_len = len(files[path])
        alloc = (ft[path][1] + 2047) // 2048 * 2048
        if len(data) > alloc:
            raise SystemExit(f'{path}: chain {len(data)} bytes > allocation {alloc}')
        old_u = sum(len(b['payload']) for b in blocks)
        new_u = sum(struct.unpack_from('<I', r, 8)[0] if (struct.unpack_from('<I', r)[0] & 0xffff) == 0x201
                    else len(r) - 8 for r in raws)
        print(f'{path}: {len(data)} / {alloc} bytes on disc; unpacked {new_u} (was {old_u}, +{new_u - old_u})')
        files[path] = bytearray(data + bytes(max(0, orig_len - len(data))))

    # ---- exe tables, packed back to back in their original region
    pos = T.EXE_TABLE_REGION[0]
    for k, j in enumerate(exe_jobs):
        payload = E.pack_table_ordered(j.codes, list(range(len(j.codes))))
        pos = (pos + 3) & ~3
        if pos + len(payload) > T.EXE_TABLE_REGION[1]:
            raise SystemExit(f'exe tables overflow at {j.tname}: need {pos + len(payload) - T.EXE_TABLE_REGION[1]} more bytes')
        exe[pos:pos + len(payload)] = payload
        struct.pack_into('<I', exe, T.EXE_TABLE_PTRS + 4 * k, T.exe_ram(pos))
        pos += len(payload)
    # the boot code also registers each table by its hard-coded address (lui/addiu a0 pairs
    # before 'jal 0x8002d08c', which turns the offsets into pointers): point those at the new spots
    new_addr = struct.unpack_from('<6I', exe, T.EXE_TABLE_PTRS)
    old_addr = [T.exe_ram(off) for off, _ in exe_tabs]
    pairs = {}
    for a in range(T.EXE_TABLE_REG_CODE[0], T.EXE_TABLE_REG_CODE[1], 4):
        o = T.exe_off(a)
        lui = struct.unpack_from('<I', exe, o)[0]
        if lui >> 16 != 0x3c04:                           # lui $a0, imm
            continue
        for d in (4, 8, 12):
            add = struct.unpack_from('<I', exe, o + d)[0]
            if add >> 16 == 0x2484:                       # addiu $a0, $a0, imm
                val = (((lui & 0xffff) << 16) + ((add & 0xffff) - (0x10000 if add & 0x8000 else 0))) & 0xffffffff
                pairs[val] = (o, o + d)
                break
    patched = 0
    for k in range(6):
        if old_addr[k] in pairs:
            o1, o2 = pairs[old_addr[k]]
            na = new_addr[k]
            lo = na & 0xffff
            hi = (na >> 16) + (1 if lo & 0x8000 else 0)
            struct.pack_into('<I', exe, o1, 0x3c040000 | (hi & 0xffff))
            struct.pack_into('<I', exe, o2, 0x24840000 | lo)
            patched += 1
    if patched != 6:
        raise SystemExit(f'exe table registration: patched {patched} of 6 references')
    free = T.EXE_TABLE_REGION[1] - pos
    exe[pos:T.EXE_TABLE_REGION[1]] = bytes(free)
    print(f'exe tables: {pos - T.EXE_TABLE_REGION[0]} bytes, {free} free')

    # ---- name entry
    rows, over = name_grid_sjis(tilecodes)
    grid = bytearray(exe[NAME_GRID:NAME_GRID + 26 * 16])
    nrows = 0
    while nrows * 26 < len(grid) and grid[nrows * 26] >= 0x81:
        nrows += 1
    keep = [bytes(grid[r * 26:(r + 1) * 26]) for r in range(nrows)]
    new_rows = (rows + keep)[:nrows]
    exe[NAME_GRID:NAME_GRID + 26 * nrows] = b''.join(new_rows)
    for sj, code in over.items():
        lead, trail = sj[0], sj[1]
        tab, base = SJIS_LEAD[lead]
        struct.pack_into('<H', exe, T.exe_off(tab) + 2 * (trail - base), code)
    print(f'name entry: {nrows} rows, {len(rows)} English')

    # glyph -> Shift-JIS (0x8004AE8C): used by the party panel's small font, the joke-name
    # check at name entry and the memory card title. Rewritten to expand name tiles (see HUD_SEG).
    cells = bytearray(4 * hud_span)
    for t in name_tiles:
        k = 4 * (tilecodes[t] - hud_base)
        cells[k:k + 4] = bytes(hud_byte(ch) for ch in t).ljust(4, b'\0')
    start = (T.EXE_TABLE_REGION[1] - len(cells)) & ~3
    if start < pos:
        raise SystemExit(f'no room for the HUD name cells ({len(cells)} bytes, {free} free)')
    exe[start:start + len(cells)] = cells
    if struct.unpack_from('<I', exe, T.exe_off(G2S_FUNC[0]))[0] != 0x27BDFFD8:
        raise SystemExit('unexpected code at the glyph->SJIS function')
    for k, w in enumerate(g2s_code(G2S_FUNC, T.exe_ram(start), hud_base, hud_span)):
        struct.pack_into('<I', exe, T.exe_off(G2S_FUNC[0]) + 4 * k, w)
    print(f'HUD names: glyph->SJIS rewritten, {len(cells)} bytes of cells at {T.exe_ram(start):#x}')

    # ---- fonts + metrics
    f13 = open(os.path.join(ROOT, 'disc', 'D', 'F0013.BIN'), 'rb').read()
    font = load_font(f13)
    mf = MenuFont(open(os.path.join(ROOT, 'disc', 'D', 'F0014.BIN'), 'rb').read())
    for t, code in tilecodes.items():
        px, W = enfont.render_tile(t)
        set_glyph(font, code, px)
        exe[WIDTH_TABLE + code] = max(1, W)
        exe[MENU_METRICS + code] = min(15, max(0, W))
        rows_ = [[1 if px[y + 1][x] != 3 else 0 for x in range(12)] for y in range(11)] + [[0] * 12]
        mf.set(code, rows_)
    for off in GAP_PATCHES:
        assert exe[off:off + 2] == b'\x01\x00', exe[off:off + 4].hex()
        exe[off:off + 2] = b'\x00\x00'

    # ---- disclaimer graphic
    import disclaimer
    f83 = open(os.path.join(ROOT, 'disc', 'D', 'F0083.BIN'), 'rb').read()
    files['D/F0083.BIN'] = bytearray(disclaimer.build(f83))
    import namegrid
    f73 = open(os.path.join(ROOT, 'disc', 'D', 'F0073.BIN'), 'rb').read()
    files['D/F0073.BIN'] = bytearray(namegrid.build(f73, NAME_ROWS)[0])

    # ---- assemble disc
    b = Builder(orig, outp)
    for path, data in files.items():
        b.replace(path, bytes(data))
    b.replace('D/F0013.BIN', build_f0013(font, f13))
    b.replace('D/F0014.BIN', mf.build())
    b.replace('SLPM_871.53', bytes(exe))
    lba16, size16 = ft['D/F0016.BIN']
    relocate = len(new16) > (size16 + 2047) // 2048 * 2048
    if not relocate:
        b.replace('D/F0016.BIN', new16)
    b.finish()
    if relocate:
        zlba, zsize = ft['ZZZ.BIN']
        with open(outp, 'r+b') as f:
            n = write_file_at(f, zlba, new16)
            set_record(f, 'D/F0016.BIN', zlba, len(new16))
            set_record(f, 'ZZZ.BIN', zlba + n, zsize - n * 2048)
            f.seek(FILEPOS_LBA * SECTOR)
            raw = bytearray(f.read(SECTOR))
            struct.pack_into('<II', raw, 24 + F0016_INDEX * 8, zlba, len(new16))
            f.seek(FILEPOS_LBA * SECTOR)
            f.write(fix_form1(raw))
        print(f'  F0016 relocated to LBA {zlba} ({n} sectors); FILEPOS.DAT and ISO directory updated')
    json.dump(tilecodes, open(os.path.join(TRANS, 'tiles.json'), 'w'), ensure_ascii=False, indent=0)


if __name__ == '__main__':
    main()
