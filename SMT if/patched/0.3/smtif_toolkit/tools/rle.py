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


def encode(width_halfwords, height, pixels):
    """Encode raw image bytes (width_halfwords*2*height) into a 0x102 RLE block."""
    import struct
    data = bytes(pixels)
    out = bytearray()
    lit = bytearray()
    i, n = 0, len(data)

    def flush():
        nonlocal lit
        while lit:
            chunk = lit[:128]
            out.append(len(chunk) - 1)
            out.extend(chunk)
            lit = lit[128:]
    while i < n:
        j = i
        while j < n and j - i < 130 and data[j] == data[i]:
            j += 1
        if j - i >= 3:
            flush()
            out.append(0x80 + (j - i) - 3)
            out.append(data[i])
            i = j
        else:
            lit.append(data[i])
            i += 1
    flush()
    return struct.pack('<IIIHH', 0x102, len(out) + 16, 0, width_halfwords, height) + bytes(out)


def _tokens(data):
    toks = []          # ['L', bytearray] or ['R', value, count]
    i, n = 0, len(data)
    while i < n:
        j = i
        while j < n and j - i < 130 and data[j] == data[i]:
            j += 1
        if j - i >= 3:
            toks.append(['R', data[i], j - i])
            i = j
        else:
            if toks and toks[-1][0] == 'L' and len(toks[-1][1]) < 128:
                toks[-1][1].append(data[i])
            else:
                toks.append(['L', bytearray([data[i]])])
            i += 1
    return toks


def _size(toks):
    return sum(1 + len(t[1]) if t[0] == 'L' else 2 for t in toks)


def encode_exact(width_halfwords, height, pixels, block_size):
    """Like encode(), but the block is exactly `block_size` bytes (header included): parts of
    runs are turned into literal bytes until the stream is long enough. Keeps a picture's
    blocks at the same offsets as the original file."""
    import struct
    toks = _tokens(bytes(pixels))
    want = block_size - 16
    if _size(toks) > want:
        raise ValueError(f'RLE stream {_size(toks)} > {want}')
    for _ in range(100000):
        grow = want - _size(toks)
        if grow == 0:
            break
        done = False
        for idx in range(1, len(toks)):            # move bytes of a run into the literal before it
            t, p = toks[idx], toks[idx - 1]
            if t[0] != 'R' or p[0] != 'L':
                continue
            take = min(grow, 128 - len(p[1]), t[2] - 3)
            if take > 0:
                p[1].extend([t[1]] * take)
                t[2] -= take
                done = True
                break
        if not done:                               # split a run: run(n) -> literal(1) + run(n-1)
            for idx, t in enumerate(toks):
                if t[0] == 'R' and t[2] > 3 and (idx == 0 or toks[idx - 1][0] != 'L' or len(toks[idx - 1][1]) >= 128):
                    t[2] -= 1
                    toks.insert(idx, ['L', bytearray([t[1]])])
                    done = True
                    break
        if not done:
            raise ValueError('cannot pad RLE stream')
    out = bytearray()
    for t in toks:
        if t[0] == 'L':
            out.append(len(t[1]) - 1)
            out.extend(t[1])
        else:
            out.append(0x80 + t[2] - 3)
            out.append(t[1])
    if len(out) != want:
        raise ValueError(f'RLE padding ended at {len(out)}, wanted {want}')
    return struct.pack('<IIIHH', 0x102, block_size, 0, width_halfwords, height) + bytes(out)
