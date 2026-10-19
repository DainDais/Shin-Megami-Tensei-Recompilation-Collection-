#!/usr/bin/env python3
"""Improved kanji matcher: common em-box crop, shift-tolerant NCC, multi-font ensemble, monotone DP."""
import sys, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(__file__))
import match_kanji as M

def render_set(chars, fp, W):
    big = 64
    font = ImageFont.truetype(fp, big, index=0)
    canv = []
    boxes = []
    for _, c in chars:
        img = Image.new('L', (big * 2, big * 2), 0)
        ImageDraw.Draw(img).text((big // 2, big // 2), c, font=font, fill=255)
        a = np.asarray(img)
        canv.append(img)
        ys, xs = np.nonzero(a > 64)
        if len(xs):
            boxes.append((xs.min(), ys.min(), xs.max(), ys.max()))
    b = np.array(boxes)
    x0, y0 = np.percentile(b[:, 0], 3), np.percentile(b[:, 1], 3)
    x1, y1 = np.percentile(b[:, 2], 97), np.percentile(b[:, 3], 97)
    out = np.zeros((len(chars), 12, 16), dtype=np.float32)
    for i, img in enumerate(canv):
        cr = img.crop((int(x0), int(y0), int(x1) + 1, int(y1) + 1)).resize((W, 12), Image.LANCZOS)
        out[i, :, 0:W] = np.asarray(cr, dtype=np.float32) / 255
    return out

def shifted(x, dx, dy):
    y = np.zeros_like(x)
    H, Wd = x.shape[1], x.shape[2]
    ys = slice(max(dy, 0), H + min(dy, 0)); yd = slice(max(-dy, 0), H + min(-dy, 0))
    xs = slice(max(dx, 0), Wd + min(dx, 0)); xd = slice(max(-dx, 0), Wd + min(-dx, 0))
    y[:, ys, xs] = x[:, yd, xd]
    return y

def main():
    data = open(sys.argv[1], 'rb').read()
    ink = M.game_glyphs(data)
    kan = ink[M.FIRST_KANJI:]
    chars = M.jis_kanji()
    fonts = ['NotoSansCJK-Regular.ttc', 'NotoSansCJK-Bold.ttc', 'NotoSerifCJK-Regular.ttc']
    W = int(sys.argv[3]) if len(sys.argv) > 3 else 13
    sim = None
    for fn in fonts:
        R = render_set(chars, '/usr/share/fonts/opentype/noto/' + fn, W)
        B = M.feats(R)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                A = M.feats(shifted(kan, dx, dy))
                s = A @ B.T
                sim = s if sim is None else np.maximum(sim, s)
    np.save(sys.argv[2] + '.sim.npy', sim)
    res = M.align(sim)
    sc = np.array([sim[i, j] for i, j in enumerate(res)])
    with open(sys.argv[2], 'w', encoding='utf-8') as f:
        f.write('glyph\tsjis\tchar\tscore\tbest_free\n')
        for i, j in enumerate(res):
            free = int(np.argmax(sim[i]))
            f.write(f'{M.FIRST_KANJI + i:04x}\t{chars[j][0]:04x}\t{chars[j][1]}\t{sc[i]:.3f}\t{chars[free][1]}\n')
    known = {0x109: '哀', 0x10a: '愛', 0x124: '一', 0x13a: '円', 0x158: '可', 0x151: '下', 0x147: '王',
             0x10b: '悪', 0x10c: '圧', 0x10d: '扱', 0x10e: '安', 0x10f: '暗', 0x110: '案', 0x111: '闇', 0x112: '以'}
    ok = sum(chars[res[g - 0x109]][1] == c for g, c in known.items())
    agree = sum(1 for i, j in enumerate(res) if int(np.argmax(sim[i])) == j)
    print('W', W, 'mean', round(float(sc.mean()), 3), 'low<0.6', int((sc < 0.6).sum()), 'known', ok, '/', len(known),
          'DP==argmax', agree, '/', len(res))
    last = chars[res[-1]]
    print('last glyph maps to', last, 'level2 count', sum(1 for j in res if chars[j][0] >= 0x989f))

main()
