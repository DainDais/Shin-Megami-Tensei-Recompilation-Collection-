#!/usr/bin/env python3
"""Patch the attract-mode movie (D/F0099.BIN) in a built disc image with the English text scroll.

usage: fmv_patch.py <original.bin> <patched.bin> [work_dir]

Needs Java and jPSXdec (https://github.com/m35/jpsxdec). Point JPSXDEC at either the
jpsxdec.jar or a directory of compiled classes (default: /home/claude/tools_ext/jpx_classes).
Steps: decode the original movie to PNG, redraw the text frames (fmv_opening.py), then let
jPSXdec re-encode only the changed macroblocks of those frames into the patched image.
The movie stays at the same sectors; every frame keeps its 10-sector slot, and jPSXdec
rewrites EDC/ECC for the sectors it touches.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
JPSXDEC = os.environ.get('JPSXDEC', '/home/claude/tools_ext/jpx_classes')


def jpx(*args, cwd=None):
    if JPSXDEC.endswith('.jar'):
        cmd = ['java', '-jar', JPSXDEC]
    else:
        cmd = ['java', '-cp', JPSXDEC, 'jpsxdec.Main']
    r = subprocess.run(cmd + list(args), cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit(f'jPSXdec failed: {" ".join(args)}')
    return r.stdout


def movie_frames(root):
    out = []
    for d, _, fs in os.walk(root):
        out += [os.path.join(d, f) for f in fs if f.startswith('F0099.BIN[0][') and f.endswith('.png')]
    return sorted(out)


def item_number(index_file, file_id):
    for line in open(index_file, encoding='utf-8', errors='replace'):
        if f'ID:{file_id}[0]|' in line and 'Type:Video' in line:
            return line.split('|')[0].split(':')[1]
    raise SystemExit(f'{file_id} not found in {index_file}')


def main():
    orig, patched = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
    work = os.path.abspath(sys.argv[3]) if len(sys.argv) > 3 else tempfile.mkdtemp(prefix='smtif_fmv_')
    os.makedirs(work, exist_ok=True)
    dec = os.path.join(work, 'decoded')
    frames = movie_frames(dec)
    if len(frames) < 1200:
        os.makedirs(dec, exist_ok=True)
        idx = os.path.join(work, 'orig.idx')
        jpx('-f', orig, '-x', idx)
        n = item_number(idx, 'D/F0099.BIN')
        jpx('-x', idx, '-f', orig, '-i', n, '-vf', 'png', '-dir', dec)
        frames = movie_frames(dec)
    src = os.path.dirname(sorted(frames)[0])
    out = os.path.join(work, 'english')
    subprocess.run([sys.executable, os.path.join(HERE, 'fmv_opening.py'), src, out], check=True)
    idx2 = os.path.join(work, 'patched.idx')
    jpx('-f', patched, '-x', idx2)
    n = item_number(idx2, 'D/F0099.BIN')
    log = jpx('-x', idx2, '-f', patched, '-i', n, '-replaceframes', os.path.join(out, 'replace.xml'))
    bad = [l for l in log.splitlines() if 'SEVERE' in l or 'Unable' in l]
    if bad:
        raise SystemExit('\n'.join(bad))
    print(f'F0099: English text scroll written ({len([f for f in os.listdir(out) if f.endswith(".png")])} frames)')


if __name__ == '__main__':
    main()
