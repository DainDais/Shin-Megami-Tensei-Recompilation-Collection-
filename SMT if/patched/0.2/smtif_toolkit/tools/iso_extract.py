#!/usr/bin/env python3
"""Extract files from a PS1 MODE2/2352 BIN image (ISO9660).

Usage: iso_extract.py <image.bin> <outdir>
Writes every file plus a listing (filelist.tsv) with LBA, size and XA flags.
"""
import os
import struct
import sys

SECTOR = 2352


def read_sector(f, lba):
    f.seek(lba * SECTOR)
    raw = f.read(SECTOR)
    return raw


def user_data(raw):
    # Mode 2: 12 sync + 4 header + 8 subheader, then 2048 (form1) or 2324 (form2)
    sub = raw[16:24]
    form2 = bool(sub[2] & 0x20)
    if form2:
        return raw[24:24 + 2324], True
    return raw[24:24 + 2048], False


def read_extent(f, lba, size):
    out = bytearray()
    n = (size + 2047) // 2048
    for i in range(n):
        d, _ = user_data(read_sector(f, lba + i))
        out += d[:2048]
    return bytes(out[:size])


def walk(f, lba, size, path, entries):
    data = read_extent(f, lba, size)
    pos = 0
    while pos < len(data):
        ln = data[pos]
        if ln == 0:
            pos = ((pos // 2048) + 1) * 2048
            continue
        rec = data[pos:pos + ln]
        e_lba = struct.unpack_from('<I', rec, 2)[0]
        e_size = struct.unpack_from('<I', rec, 10)[0]
        flags = rec[25]
        nlen = rec[32]
        name = rec[33:33 + nlen]
        # XA system use area
        su_off = 33 + nlen + (1 - nlen % 2)
        xa_attr = 0
        if su_off + 14 <= ln and rec[su_off + 6:su_off + 8] == b'XA':
            xa_attr = struct.unpack_from('>H', rec, su_off + 4)[0]
        pos += ln
        if name in (b'\x00', b'\x01'):
            continue
        name = name.decode('ascii', 'replace').split(';')[0]
        full = f"{path}/{name}" if path else name
        if flags & 2:
            entries.append((full + '/', e_lba, e_size, xa_attr, True))
            walk(f, e_lba, e_size, full, entries)
        else:
            entries.append((full, e_lba, e_size, xa_attr, False))


def main():
    img, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    with open(img, 'rb') as f:
        pvd, _ = user_data(read_sector(f, 16))
        assert pvd[1:6] == b'CD001', 'no ISO9660 PVD'
        root = pvd[156:156 + 34]
        r_lba = struct.unpack_from('<I', root, 2)[0]
        r_size = struct.unpack_from('<I', root, 10)[0]
        entries = []
        walk(f, r_lba, r_size, '', entries)
        with open(os.path.join(outdir, 'filelist.tsv'), 'w') as lst:
            lst.write('path\tlba\tsize\txa_attr\n')
            for full, lba, size, xa, isdir in entries:
                lst.write(f"{full}\t{lba}\t{size}\t{xa:04x}\n")
                if isdir:
                    os.makedirs(os.path.join(outdir, full), exist_ok=True)
                    continue
                # XA/STR (form2 interleaved) files: dump raw sectors instead
                is_raw = bool(xa & 0x3000) and not (xa & 0x0800) or bool(xa & 0x4000)
                dst = os.path.join(outdir, full)
                os.makedirs(os.path.dirname(dst) or outdir, exist_ok=True)
                if is_raw:
                    n = (size + 2047) // 2048
                    with open(dst + '.raw', 'wb') as o:
                        for i in range(n):
                            o.write(read_sector(f, lba + i))
                else:
                    with open(dst, 'wb') as o:
                        o.write(read_extent(f, lba, size))
        print(f"{len(entries)} entries")


if __name__ == '__main__':
    main()
