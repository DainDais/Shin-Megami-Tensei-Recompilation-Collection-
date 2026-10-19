#!/usr/bin/env python3
"""Map the game's kanji glyphs (JIS-ordered subset) to Unicode.

Renders every JIS X 0208 kanji with a CJK font, scores similarity against each
game glyph, then picks the best strictly-increasing alignment with DP.
Usage: match_kanji.py font_raw.bin base_table.txt out_table.tsv
"""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

GW, GH, GSZ = 16, 12, 48
FIRST_KANJI = 0x109


def game_glyphs(data):
    n = len(data) // GSZ
    arr = np.frombuffer(data, dtype=np.uint8).reshape(n, GSZ)
    out = np.zeros((n, GH, GW), dtype=np.float32)
    for k in range(4):  # 2bpp LSB-first, 4 px per byte
        out[:, :, k::4] = ((arr.reshape(n, GH, 4) >> (2 * k)) & 3)
    ink = (3 - out) / 3.0
    ink[:, :, 14:] = 0  # padding columns
    return ink


def jis_kanji():
    chars = []
    for hi in list(range(0x88, 0xa0)) + list(range(0xe0, 0xeb)):
        for lo in list(range(0x40, 0x7f)) + list(range(0x80, 0xfd)):
            if hi == 0x88 and lo < 0x9f:
                continue
            try:
                c = bytes([hi, lo]).decode('shift_jis')
            except UnicodeDecodeError:
                continue
            chars.append((hi << 8 | lo, c))
    return chars


def render(chars, fontpath, idx):
    big = 48
    font = ImageFont.truetype(fontpath, big, index=idx)
    out = np.zeros((len(chars), GH, GW), dtype=np.float32)
    for i, (_, c) in enumerate(chars):
        img = Image.new('L', (big, big), 0)
        ImageDraw.Draw(img).text((0, -big * 0.12), c, font=font, fill=255)
        small = img.resize((12, 12), Image.LANCZOS)
        a = np.asarray(small, dtype=np.float32) / 255.0
        out[i, :, 1:13] = a
    return out


def feats(x):
    # blur a little, flatten, z-normalize
    from numpy.lib.stride_tricks import sliding_window_view  # noqa
    k = np.array([0.25, 0.5, 0.25], dtype=np.float32)
    y = x.copy()
    y = (np.pad(y, ((0, 0), (0, 0), (1, 1)))[:, :, :-2] * k[0] + y * k[1] +
         np.pad(y, ((0, 0), (0, 0), (1, 1)))[:, :, 2:] * k[2])
    y = (np.pad(y, ((0, 0), (1, 1), (0, 0)))[:, :-2] * k[0] + y * k[1] +
         np.pad(y, ((0, 0), (1, 1), (0, 0)))[:, 2:] * k[2])
    f = y.reshape(len(y), -1)
    f = f - f.mean(1, keepdims=True)
    f /= (np.linalg.norm(f, axis=1, keepdims=True) + 1e-6)
    return f


def align(sim):
    n, m = sim.shape
    NEG = -1e9
    prev = np.full(m + 1, 0.0)  # dp for row -1: zero everywhere
    back = np.zeros((n, m), dtype=np.int32)
    rows = []
    for i in range(n):
        cand = np.full(m, NEG)
        cand[:] = prev[:-1] + sim[i]  # take j for glyph i, previous used < j
        if i == 0:
            cand = sim[i].copy()
        best_upto = np.maximum.accumulate(cand)
        arg = np.zeros(m, dtype=np.int64)
        # argmax of running max
        idx = np.arange(m)
        is_new = cand >= best_upto
        arg = np.maximum.accumulate(np.where(is_new, idx, 0))
        back[i] = arg
        newprev = np.full(m + 1, NEG)
        newprev[1:] = best_upto
        rows.append(newprev)
        prev = newprev
    # traceback
    res = [0] * n
    j = int(np.argmax(prev[1:]))
    for i in range(n - 1, -1, -1):
        jj = back[i][j]
        res[i] = int(jj)
        j = jj - 1
    return res


def main():
    data = open(sys.argv[1], 'rb').read()
    ink = game_glyphs(data)
    kan = ink[FIRST_KANJI:]
    chars = jis_kanji()
    fontpath = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
    rend = render(chars, fontpath, 0)  # index 0 = JP in Noto Sans CJK ttc
    A, B = feats(kan), feats(rend)
    sim = A @ B.T
    res = align(sim)
    with open(sys.argv[3], 'w', encoding='utf-8') as f:
        f.write('glyph\tsjis\tchar\tscore\tbest_free\n')
        for i, j in enumerate(res):
            g = FIRST_KANJI + i
            free = int(np.argmax(sim[i]))
            f.write(f'{g:04x}\t{chars[j][0]:04x}\t{chars[j][1]}\t{sim[i, j]:.3f}\t{chars[free][1]}\n')
    sc = np.array([sim[i, j] for i, j in enumerate(res)])
    print('glyphs', len(res), 'mean score', sc.mean(), 'low(<0.5)', int((sc < 0.5).sum()))


if __name__ == '__main__':
    main()
