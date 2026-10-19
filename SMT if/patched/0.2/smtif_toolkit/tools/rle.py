"""RLE image codec (magic 0x102) used by SMT if... (PS1) graphics.

Header: u32 0x102, u32 packed_size?, u32 0, u16 width_in_halfwords, u16 height, then stream:
  c < 0x80  -> c+1 literal bytes
  c >= 0x80 -> repeat next byte (c - 0x80 + 3) times   (verified against block sizes)
"""
import struct


def decode(src, pos=0, run_bias=3):
    magic, size, z = struct.unpack_from('<III', src, pos)
    w, h = struct.unpack_from('<HH', src, pos + 12)
    need = w * 2 * h
    p = pos + 16
    out = bytearray()
    while len(out) < need:
        c = src[p]
        p += 1
        if c < 0x80:
            out += src[p:p + c + 1]
            p += c + 1
        else:
            out += bytes([src[p]]) * (c - 0x80 + run_bias)
            p += 1
    return w, h, bytes(out[:need]), p - pos
