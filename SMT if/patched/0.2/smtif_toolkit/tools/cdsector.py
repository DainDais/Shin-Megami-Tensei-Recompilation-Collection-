"""CD-ROM Mode 2 Form 1 sector helpers: EDC/ECC regeneration and in-place file patching.

Algorithms follow ECMA-130 (as used by ECM tools): EDC is a reflected CRC-32
(poly 0xD8018001), ECC is the P/Q Reed-Solomon product code over GF(2^8).
For Mode 2 the 4-byte header is treated as zero when computing ECC.
"""
SECTOR = 2352

_edc_lut = []
for i in range(256):
    e = i
    for _ in range(8):
        e = (e >> 1) ^ (0xD8018001 if e & 1 else 0)
    _edc_lut.append(e)

_f_lut = [0] * 256
_b_lut = [0] * 256
for i in range(256):
    j = (i << 1) ^ (0x11D if i & 0x80 else 0)
    _f_lut[i] = j & 0xFF
    _b_lut[i ^ j & 0xFF] = i


def edc(data):
    e = 0
    for b in data:
        e = (e >> 8) ^ _edc_lut[(e ^ b) & 0xFF]
    return e


def _ecc_pq(buf, major_count, minor_count, major_mult, minor_inc, dest):
    size = major_count * minor_count
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        ecc_a = ecc_b = 0
        for _ in range(minor_count):
            temp = buf[index]
            index += minor_inc
            if index >= size:
                index -= size
            ecc_a ^= temp
            ecc_b ^= temp
            ecc_a = _f_lut[ecc_a]
        ecc_a = _b_lut[_f_lut[ecc_a] ^ ecc_b]
        buf[dest + major] = ecc_a
        buf[dest + major + major_count] = ecc_a ^ ecc_b


def fix_form1(sector):
    """Recompute EDC+ECC for a Mode 2 Form 1 raw sector (bytearray, 2352 bytes)."""
    s = bytearray(sector)
    e = edc(s[16:16 + 8 + 2048])
    s[2072:2076] = e.to_bytes(4, 'little')
    hdr = bytes(s[12:16])
    s[12:16] = b'\0\0\0\0'
    # ECC operates on bytes 12..2075 (header+subheader+data+edc), P then Q
    region = s[12:]  # view copy
    buf = bytearray(region)
    # P parity: 86 x 24, written at offset 2076-12
    _ecc_pq(buf, 86, 24, 2, 86, 2076 - 12)
    # Q parity: 52 x 43
    _ecc_pq(buf, 52, 43, 86, 88, 2076 - 12 + 172)
    s[12:] = buf
    s[12:16] = hdr
    return bytes(s)


def is_form2(sector):
    return bool(sector[18] & 0x20)


class Disc:
    def __init__(self, path):
        self.f = open(path, 'r+b')

    def read_raw(self, lba):
        self.f.seek(lba * SECTOR)
        return self.f.read(SECTOR)

    def write_user(self, lba, data):
        """Write up to 2048 bytes of user data into a Form 1 sector, regenerating EDC/ECC."""
        raw = bytearray(self.read_raw(lba))
        assert not is_form2(raw), f'LBA {lba} is Form 2'
        d = bytes(data).ljust(2048, b'\0')
        raw[24:24 + 2048] = d
        self.f.seek(lba * SECTOR)
        self.f.write(fix_form1(raw))

    def write_file(self, lba, alloc_bytes, data):
        """Overwrite a file's sectors in place; data must fit its original sector allocation."""
        n_alloc = (alloc_bytes + 2047) // 2048
        assert len(data) <= n_alloc * 2048, f'file grew past allocation ({len(data)} > {n_alloc * 2048})'
        for i in range(n_alloc):
            self.write_user(lba + i, data[i * 2048:(i + 1) * 2048])

    def close(self):
        self.f.close()
