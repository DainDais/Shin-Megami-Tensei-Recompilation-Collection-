#!/usr/bin/env python3
"""Replace the Japanese text scroll in the attract-mode movie (D/F0099.BIN) with English.

The scroll is baked into the MDEC video, so it is fixed frame by frame:
  1. Decode the movie to PNGs with jPSXdec (decoded/ dir).
  2. Rebuild the scrolling Japanese "page" (it moves up exactly 0.5 px per frame)
     and from it a mask of where the Japanese text sits in every frame.
  3. Paint the clean background back under the mask: a text-free plate while the
     camera is still, a motion-matched plate or later frame once it starts tilting.
  4. Draw the English page (fmv/opening_text.json) with the same scroll and clipping.
  5. Write PNGs plus a jPSXdec partial-replace XML (only changed macroblocks are
     re-encoded; every frame keeps its 10-sector slot).

usage: fmv_opening.py <decoded_dir> <out_dir> [text.json]
"""
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'
FONT_SIZE = 13
INK = (236, 236, 236)
F0 = 88                 # frame where page row == screen row
WIN = (164, 214)        # visible text window rows [top, bottom)
FIRST, LAST = 60, 596   # frames that can show text
STILL_END = 534         # camera is still up to here
AFFINE_END = 560        # affine fit of the plate is good up to here
CLEAN_REF = 594         # first text-free frame after the scroll
PAGE_H = 520


def frame_path(d, i):
    return os.path.join(d, f'F0099.BIN[0][{i:04d}].png')


def load(d, i):
    return np.asarray(Image.open(frame_path(d, i)).convert('RGB'), dtype=np.float32)


def scroll(f):
    return (f - F0) / 2.0


def page_rows(f):
    """For each window row y: (page row floor, page row ceil, frac)."""
    s = scroll(f)
    ys = np.arange(WIN[0], WIN[1])
    p = ys + s
    return ys, np.floor(p).astype(int), np.ceil(p).astype(int), p - np.floor(p)


def build_jp_mask(d, plate):
    acc = np.zeros((PAGE_H, 320))
    cnt = np.zeros((PAGE_H, 1))
    for f in range(FIRST, STILL_END, 2):
        diff = np.abs(load(d, f) - plate).max(axis=2) > 28
        ys, p0, _, _ = page_rows(f)
        ok = (p0 >= 0) & (p0 < PAGE_H)
        acc[p0[ok]] += diff[ys[ok]]
        cnt[p0[ok]] += 1
    frac = acc / np.maximum(cnt, 1)
    m = (frac > 0.45).astype(np.uint8)
    m = cv2.dilate(m, np.ones((3, 3), np.uint8), iterations=1)
    return m


def render_en_page(lines):
    font = ImageFont.truetype(FONT, FONT_SIZE)
    layer = Image.new('L', (320, PAGE_H), 0)
    dr = ImageDraw.Draw(layer)
    for ln in lines:
        w = dr.textlength(ln['text'], font=font)
        if ln['x'] + w > 316:
            raise SystemExit(f"line too wide ({ln['x'] + w:.0f}px): {ln['text']}")
        # Liberation's ascent puts caps ~3px below the draw origin; JP glyph tops sit at y
        dr.text((ln['x'], ln['y'] - 2), ln['text'], font=font, fill=255)
    return np.asarray(layer, dtype=np.float32) / 255.0


def sample_page(page, f):
    """Window-sized slice of a page at frame f (linear interp for half-pixel steps)."""
    ys, p0, p1, fr = page_rows(f)
    out = np.zeros((len(ys),) + page.shape[1:], dtype=np.float32)
    ok = (p0 >= 0) & (p1 < page.shape[0])
    a = page[p0[ok]].astype(np.float32)
    b = page[p1[ok]].astype(np.float32)
    w = fr[ok].reshape((-1,) + (1,) * (page.ndim - 1))
    out[ok] = a * (1 - w) + b * w
    return out


def ecc(ref, img, mode, mask):
    g0 = cv2.cvtColor(ref.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    g1 = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    W = np.eye(3, 3, dtype=np.float32) if mode == cv2.MOTION_HOMOGRAPHY else np.eye(2, 3, dtype=np.float32)
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 300, 1e-6)
    cc, W = cv2.findTransformECC(g0, g1, W, mode, crit, mask, 5)
    if mode == cv2.MOTION_HOMOGRAPHY:
        bg = cv2.warpPerspective(ref, W, (320, 240), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP)
    else:
        bg = cv2.warpAffine(ref, W, (320, 240), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP)
    return cc, bg


def block_fill(img, mask, refs, bw=16, margin=6, dy_rng=(-36, 36), dx_rng=(-6, 6)):
    """Fill masked pixels block by block from the best-matching offset in any reference
    frame, judged on the unmasked pixels around the block (handles parallax)."""
    out = img.copy()
    H, W = mask.shape
    rows = np.where(mask.any(axis=1))[0]
    if not len(rows):
        return out, 0
    y0, y1 = rows.min(), rows.max() + 1
    worst = 0
    for x0 in range(0, W, bw):
        x1 = min(W, x0 + bw)
        if not mask[y0:y1, x0:x1].any():
            continue
        ya, yb = max(0, y0 - margin), min(H, y1 + margin)
        xa, xb = max(0, x0 - margin), min(W, x1 + margin)
        tgt = img[ya:yb, xa:xb]
        known = ~cv2.dilate(mask[ya:yb, xa:xb].astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        best = None
        for ref in refs:
            for dy in range(dy_rng[0], dy_rng[1] + 1):
                if ya + dy < 0 or yb + dy > H:
                    continue
                for dx in range(dx_rng[0], dx_rng[1] + 1):
                    if xa + dx < 0 or xb + dx > W:
                        continue
                    cand = ref[ya + dy:yb + dy, xa + dx:xb + dx]
                    e = np.mean(np.abs(cand - tgt)[known]) if known.any() else 0
                    if best is None or e < best[0]:
                        best = (e, ref, dy, dx)
        e, ref, dy, dx = best
        worst = max(worst, e)
        mb = mask[ya:yb, xa:xb]
        sub = out[ya:yb, xa:xb]
        sub[mb] = ref[ya + dy:yb + dy, xa + dx:xb + dx][mb]
    return out, worst


def main():
    src, out = sys.argv[1], sys.argv[2]
    text = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(__file__), '..', 'fmv', 'opening_text.json')
    lines = json.load(open(text, encoding='utf-8'))['lines']
    os.makedirs(out, exist_ok=True)

    plate = np.median(np.stack([load(src, i) for i in range(35, 59)]), axis=0)
    jp_mask = build_jp_mask(src, plate)
    en = render_en_page(lines)
    clean_ref = load(src, CLEAN_REF)

    xml = ['<?xml version="1.0"?>', '<str-replace version="0.3">']
    report = []
    prev = plate
    for f in range(FIRST, LAST + 1):
        img = load(src, f)
        ys = np.arange(WIN[0], WIN[1])
        m = sample_page(jp_mask.astype(np.float32), f) > 0.01      # union of floor/ceil rows
        mask = np.zeros((240, 320), bool)
        mask[ys] = m
        en_a = sample_page(en, f)
        if not mask.any() and en_a.max() == 0:
            continue
        if f <= STILL_END:
            new = img.copy()
            new[mask] = plate[mask]
            how = 'plate'
        else:
            # camera is moving (with parallax): fill block by block from the plate,
            # the first text-free frame, or the previous fixed frame
            new, err = block_fill(img, mask, [plate, clean_ref, prev])
            how = f'blocks err {err:.1f}'
        prev = new.copy()
        a = np.zeros((240, 320, 1), np.float32)
        a[ys, :, 0] = en_a
        new = new * (1 - a) + np.array(INK, np.float32) * a
        Image.fromarray(np.clip(new + 0.5, 0, 255).astype(np.uint8)).save(os.path.join(out, f'{f:04d}.png'))
        xml.append(f'  <partial-replace frame="{f}" tolerance="3" rect="0,{WIN[0] - 8},320,{WIN[1] - WIN[0] + 16}">'
                   f'{os.path.abspath(os.path.join(out, f"{f:04d}.png"))}</partial-replace>')
        report.append(f'{f} {how}')
    xml.append('</str-replace>')
    open(os.path.join(out, 'replace.xml'), 'w').write('\n'.join(xml) + '\n')
    open(os.path.join(out, 'report.txt'), 'w').write('\n'.join(report) + '\n')
    print(f'{len(report)} frames written to {out}')


if __name__ == '__main__':
    main()
