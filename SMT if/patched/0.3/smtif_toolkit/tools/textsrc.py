#!/usr/bin/env python3
"""Every text source on the disc, in one place.

- block chains: a file is a run of 4-byte-aligned blocks, each
    raw:  u32 magic (low half 0x0001), u32 size incl. 8-byte header, payload
    LZ:   u32 magic (low half 0x0201), u32 size incl. 12-byte header, u32 unpacked size, stream
  The high half of the magic is a block index the loader keeps (F0094 uses 1..6).
  The game's loader accepts either form for any block, so translated raw blocks are
  stored as LZ to save space.
- string table payload: u32 offsets[n] (offsets[0] == 4n) + FFFF-terminated LE16 strings.
- executable tables: six raw string tables (no header) addressed by a pointer array.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lz import decompress, compress  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DISC = os.path.join(HERE, '..', 'disc')

EXE_LOAD = 0x80010000
EXE_HDR = 0x800
EXE_TABLE_PTRS = 0xE853C          # u32[6] -> the six message tables below
EXE_TABLE_REGION = (0xE5B78, 0xE853C)   # the tables are packed back to back in here
EXE_TABLE_REG_CODE = (0x8006A404, 0x8006A464)   # boot code that registers each table by address


def exe_off(ram):
    return ram - EXE_LOAD + EXE_HDR


def exe_ram(off):
    return off - EXE_HDR + EXE_LOAD


def parse_table(payload):
    """-> list of code lists, or None if payload is not a string table."""
    if len(payload) < 4:
        return None
    first = struct.unpack_from('<I', payload, 0)[0]
    if first == 0 or first % 4 or first >= len(payload):
        return None
    n = first // 4
    offs = struct.unpack_from(f'<{n}I', payload, 0)
    out = []
    for o in offs:
        if o % 2 or o < first or o >= len(payload):
            return None
        codes = []
        e = o
        while True:
            if e + 1 >= len(payload):
                return None
            c = payload[e] | payload[e + 1] << 8
            if c == 0xFFFF:
                break
            codes.append(c)
            e += 2
        out.append(codes)
    return out


def table_extent(payload):
    """Bytes actually covered by a table (offsets + furthest string end)."""
    first = struct.unpack_from('<I', payload, 0)[0]
    n = first // 4
    offs = struct.unpack_from(f'<{n}I', payload, 0)
    end = first
    for o in offs:
        e = o
        while payload[e] | payload[e + 1] << 8 != 0xFFFF:
            e += 2
        end = max(end, e + 2)
    return end


def read_chain(data, start=0):
    """Parse a block chain -> list of dicts {off, magic, kind, payload, raw}."""
    blocks = []
    pos = start
    while pos + 8 <= len(data):
        magic, size = struct.unpack_from('<II', data, pos)
        lo = magic & 0xFFFF
        if lo == 0x0001 and 8 < size <= len(data) - pos:
            blocks.append(dict(off=pos, magic=magic, kind='raw', payload=bytes(data[pos + 8:pos + size]),
                               raw=bytes(data[pos:pos + size])))
        elif lo == 0x0201 and 12 <= size <= len(data) - pos:
            usize = struct.unpack_from('<I', data, pos + 8)[0]
            payload, end = decompress(data, pos + 12, usize)
            if end - pos != size:
                break
            blocks.append(dict(off=pos, magic=magic, kind='lz', payload=payload, raw=bytes(data[pos:pos + size])))
        else:
            break
        pos = (pos + size + 3) & ~3
    return blocks


def pack_lz(magic, payload):
    body = compress(payload)
    return struct.pack('<III', (magic & 0xFFFF0000) | 0x0201, len(body) + 12, len(payload)) + body


def write_chain(blocks):
    """blocks: list of raw block bytes -> chain bytes (4-byte aligned)."""
    out = bytearray()
    for b in blocks:
        out += b
        while len(out) % 4:
            out += b'\0'
    return bytes(out)


def exe_tables(exe):
    """-> list of (table_offset_in_exe, payload_bytes) for the six exe message tables."""
    ptrs = struct.unpack_from('<6I', exe, EXE_TABLE_PTRS)
    out = []
    for p in ptrs:
        off = exe_off(p)
        # extent: parse with a generous window
        payload = bytes(exe[off:off + 0x2000])
        ext = table_extent(payload)
        out.append((off, payload[:ext]))
    return out
