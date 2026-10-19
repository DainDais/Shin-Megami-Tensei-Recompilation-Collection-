#!/usr/bin/env python3
"""Rebuild a patched disc image by rewriting files in place (same LBA, same allocation).

Library use:
    b = Builder(orig_bin, out_bin)
    b.replace('D/F0013.BIN', data)   # data <= original sector allocation
    b.patch_exe(offset, bytes)       # SLPM_871.53 byte patch
    b.finish()
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdsector import Disc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DISC_DIR = os.path.join(HERE, '..', 'disc')


def file_table():
    t = {}
    for line in open(os.path.join(DISC_DIR, 'filelist.tsv')).read().split('\n')[1:]:
        if not line.strip():
            continue
        p, lba, size, xa = line.split('\t')
        t[p] = (int(lba), int(size))
    return t


class Builder:
    def __init__(self, orig, out):
        shutil.copyfile(orig, out)
        self.out = out
        self.ft = file_table()
        self.files = {}

    def get(self, path):
        if path not in self.files:
            self.files[path] = bytearray(open(os.path.join(DISC_DIR, path), 'rb').read())
        return self.files[path]

    def replace(self, path, data):
        lba, size = self.ft[path]
        alloc = (size + 2047) // 2048 * 2048
        if len(data) > alloc:
            raise ValueError(f'{path}: {len(data)} bytes > allocation {alloc}')
        self.files[path] = bytearray(data)

    def patch(self, path, offset, data):
        buf = self.get(path)
        buf[offset:offset + len(data)] = data

    def finish(self):
        d = Disc(self.out)
        for path, data in self.files.items():
            lba, size = self.ft[path]
            orig = open(os.path.join(DISC_DIR, path), 'rb').read()
            # keep original bytes beyond our data inside the allocation
            alloc = (size + 2047) // 2048 * 2048
            full = bytearray(alloc)
            full[:len(orig)] = orig
            full[:len(data)] = data
            if len(data) < len(orig):
                full[len(data):len(orig)] = orig[len(data):]
            changed = 0
            for i in range(alloc // 2048):
                new = bytes(full[i * 2048:(i + 1) * 2048])
                old = orig[i * 2048:(i + 1) * 2048].ljust(2048, b'\0')
                if new != old:
                    d.write_user(lba + i, new)
                    changed += 1
            print(f'  {path}: {changed} sectors rewritten')
        d.close()
