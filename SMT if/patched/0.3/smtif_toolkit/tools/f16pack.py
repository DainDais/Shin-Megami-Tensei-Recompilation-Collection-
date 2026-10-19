"""F0016 (event scripts) parser/repacker.

Layout: the exe holds an index at EXE_INDEX of u32 entries (low 24 bits = byte offset into F0016,
high byte = tag 4; last entry tag 0 = file size). Each index entry starts a sector-aligned "unit";
a unit's length is the gap to the next entry. A unit is a sequence of 4-byte-aligned blocks:
  magic 0x201 (LZ):  [u32 magic][u32 total size incl. header][u32 unpacked size][stream]
  magic 0x001 (raw): [u32 1][u32 total size incl. header][payload]
Text payloads are string tables: u32 offsets[n] (relative to table start) + 0xFFFF-terminated u16 strings.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lz import decompress, pack_block  # noqa: E402

EXE_INDEX = 0xe4cf4
MAX_UNIT_SECTORS = 6
MAX_TEXT_USIZE = 0x14fa


def read_index(exe):
    ents = []
    i = EXE_INDEX
    while True:
        v = struct.unpack_from('<I', exe, i)[0]
        ents.append(v)
        i += 4
        if v >> 24 == 0:
            return ents


def parse_unit(data):
    """Return list of blocks: dict(kind, raw, payload)."""
    blocks = []
    p = 0
    while p + 8 <= len(data):
        magic, size = struct.unpack_from('<II', data, p)
        if magic & 0xffff == 0x201 and size == 8:
            blocks.append({'kind': 'empty', 'magic': magic, 'raw': data[p:p + 8], 'payload': b''})
        elif magic & 0xffff == 0x201 and 12 < size <= len(data) - p:
            usz = struct.unpack_from('<I', data, p + 8)[0]
            payload, _ = decompress(data, p + 12, usz)
            blocks.append({'kind': 'lz', 'magic': magic, 'raw': data[p:p + size], 'payload': payload})
        elif magic == 1 and 8 < size <= len(data) - p:
            blocks.append({'kind': 'raw', 'magic': magic, 'raw': data[p:p + size], 'payload': data[p + 8:p + size]})
        else:
            break
        p = (p + size + 3) & ~3
    tail = data[p:].rstrip(b'\0')
    return blocks, tail


def parse_table(payload):
    """String table -> list of code lists, or None if not a table."""
    if len(payload) < 6:
        return None
    first = struct.unpack_from('<I', payload, 0)[0]
    if first == 0 or first % 4 or first > len(payload):
        return None
    n = first // 4
    offs = struct.unpack_from(f'<{n}I', payload, 0)
    if any(o > len(payload) or o % 2 or o < first for o in offs):
        return None
    out = []
    for o in offs:
        codes = []
        while o + 1 < len(payload):
            c = struct.unpack_from('<H', payload, o)[0]
            if c == 0xffff:
                break
            codes.append(c)
            o += 2
        out.append(codes)
    return out


def build_block(kind, magic, payload):
    if kind == 'lz':
        b = bytearray(pack_block(payload))
        struct.pack_into('<I', b, 0, magic)
        return bytes(b)
    return struct.pack('<II', magic, len(payload) + 8) + payload


def load(exe, f16):
    ents = read_index(exe)
    offs = [v & 0xffffff for v in ents]
    units = []
    for k in range(len(ents) - 1):
        a, b = offs[k], offs[k + 1]
        blocks, tail = parse_unit(f16[a:b])
        units.append({'tag': ents[k] >> 24, 'off': a, 'end': b, 'blocks': blocks, 'tail': tail,
                      'data': f16[a:b], 'dirty': False})
    return units, ents[-1]


def replace_text(unit, block_index, payload):
    blk = unit['blocks'][block_index]
    if len(payload) > MAX_TEXT_USIZE:
        raise ValueError(f'unit {unit["off"]:#x} block {block_index}: text {len(payload)} > {MAX_TEXT_USIZE}')
    blk['payload'] = payload
    blk['raw'] = build_block(blk['kind'], blk['magic'], payload)
    unit['dirty'] = True


def unit_bytes(unit):
    if not unit['dirty']:
        return unit['data'].rstrip(b'\0') or unit['data'][:1]
    out = bytearray()
    for blk in unit['blocks']:
        while len(out) % 4:
            out.append(0)
        out += blk['raw']
    if unit['tail']:
        raise ValueError(f'unit {unit["off"]:#x} has unparsed trailing data')
    return bytes(out)


def repack(units, end_marker):
    """Return (new F0016 bytes, new index u32 list)."""
    out = bytearray()
    index = []
    for u in units:
        body = unit_bytes(u)
        if not u['dirty']:
            # keep original sector span for untouched units
            span = u['end'] - u['off']
            body = u['data']
        else:
            span = (len(body) + 0x7ff) // 0x800 * 0x800
            orig_span = u['end'] - u['off']
            span = max(span, orig_span)
            if span // 0x800 > MAX_UNIT_SECTORS:
                raise ValueError(f'unit {u["off"]:#x} needs {span // 0x800} sectors > {MAX_UNIT_SECTORS}')
            body = body + bytes(span - len(body))
        index.append((u['tag'] << 24) | len(out))
        out += body
    index.append((end_marker >> 24 << 24) | len(out))
    return bytes(out), index
