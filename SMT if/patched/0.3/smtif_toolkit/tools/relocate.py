"""Move files on the disc image: ISO9660 directory records + FILEPOS.DAT updates."""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdsector import SECTOR, fix_form1, write_form1  # noqa: E402


def _user(f, lba):
    f.seek(lba * SECTOR)
    return f.read(SECTOR)[24:24 + 2048]


def find_record(f, path):
    """Return (dir_lba_of_sector, byte_offset_in_sector) of the directory record for `path`."""
    pvd = _user(f, 16)
    root = pvd[156:156 + 34]
    lba, size = struct.unpack_from('<I', root, 2)[0], struct.unpack_from('<I', root, 10)[0]
    parts = path.split('/')
    for depth, name in enumerate(parts):
        found = None
        for s in range((size + 2047) // 2048):
            sec = _user(f, lba + s)
            p = 0
            while p < 2048:
                ln = sec[p]
                if ln == 0:
                    break
                nl = sec[p + 32]
                nm = sec[p + 33:p + 33 + nl].decode('ascii', 'replace').split(';')[0]
                if nm == name:
                    found = (lba + s, p, struct.unpack_from('<I', sec, p + 2)[0], struct.unpack_from('<I', sec, p + 10)[0])
                    break
                p += ln
            if found:
                break
        if not found:
            raise KeyError(path)
        if depth < len(parts) - 1:
            lba, size = found[2], found[3]
    return found[0], found[1]


def set_record(f, path, new_lba, new_size):
    sec_lba, off = find_record(f, path)
    f.seek(sec_lba * SECTOR)
    raw = bytearray(f.read(SECTOR))
    b = 24 + off
    raw[b + 2:b + 6] = struct.pack('<I', new_lba)
    raw[b + 6:b + 10] = struct.pack('>I', new_lba)
    raw[b + 10:b + 14] = struct.pack('<I', new_size)
    raw[b + 14:b + 18] = struct.pack('>I', new_size)
    f.seek(sec_lba * SECTOR)
    f.write(fix_form1(raw))


def write_file_at(f, lba, data):
    n = (len(data) + 2047) // 2048
    for i in range(n):
        last = (i == n - 1)
        write_form1(f, lba + i, data[i * 2048:(i + 1) * 2048], 0x89 if last else 0x08)
    return n
