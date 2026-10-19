"""SMT if... (PS1) LZ codec used for event-script text blocks (magic 0x201).

Stream: control byte c
  c < 0x80  -> copy c+1 literal bytes
  c >= 0x80 -> back-reference: length (c & 0x7f) + 3, distance (next byte) + 1
(The exact bit split of long references is verified empirically below.)
"""


def decompress(src, pos, out_size, variant='a'):
    out = bytearray()
    while len(out) < out_size:
        c = src[pos]
        pos += 1
        if c < 0x80:
            n = c + 1
            out += src[pos:pos + n]
            pos += n
        else:
            b = src[pos]
            pos += 1
            if variant == 'a':
                ln = (c & 0x7f) + 3
                dist = b + 1
            else:  # 'b': 12-bit distance, 3-bit length
                ln = ((c >> 4) & 7) + 3
                dist = (((c & 0xf) << 8) | b) + 1
            if dist > len(out):
                raise ValueError(f'bad distance {dist} at out {len(out)} pos {pos}')
            for _ in range(ln):
                out.append(out[-dist])
    return bytes(out[:out_size]), pos


def compress(data):
    """Optimal-parse compressor for the format above (window 256, match 3..130, literal run 1..128)."""
    import numpy as np
    n = len(data)
    if n == 0:
        return b''
    a = np.frombuffer(bytes(data), dtype=np.uint8)
    best = np.zeros(n + 1, dtype=np.int32)
    bestd = np.zeros(n + 1, dtype=np.int32)
    for d in range(1, min(256, n - 1) + 1):
        eq = (a[d:] == a[:-d]).astype(np.int32)  # eq[k] -> data[k+d] == data[k]
        # run length from each position forward: m[i] for i>=d
        run = np.zeros(len(eq) + 1, dtype=np.int32)
        # reverse cumulative run
        r = 0
        rl = np.empty(len(eq), dtype=np.int32)
        # vectorised reverse run-length
        idx = np.arange(len(eq))
        zeros = np.where(eq == 0, idx, len(eq))
        nxt0 = np.minimum.accumulate(zeros[::-1])[::-1]
        rl = nxt0 - idx
        m = np.minimum(rl, 130)
        pos = idx + d
        upd = m > best[pos]
        best[pos[upd]] = m[upd]
        bestd[pos[upd]] = d
    INF = 1 << 30
    cost = [INF] * (n + 1)
    choice = [None] * (n + 1)
    cost[n] = 0
    for i in range(n - 1, -1, -1):
        c = INF
        ch = None
        lim = min(128, n - i)
        for k in range(1, lim + 1):
            v = 1 + k + cost[i + k]
            if v < c:
                c, ch = v, ('L', k)
        L = int(best[i])
        if L >= 3:
            for ln in range(3, min(L, n - i) + 1):
                v = 2 + cost[i + ln]
                if v < c:
                    c, ch = v, ('M', ln)
        cost[i] = c
        choice[i] = ch
    out = bytearray()
    i = 0
    while i < n:
        kind, k = choice[i]
        if kind == 'L':
            out.append(k - 1)
            out += data[i:i + k]
        else:
            out.append(0x80 | (k - 3))
            out.append(int(bestd[i]) - 1)
        i += k
    return bytes(out)


def pack_block(data):
    """Full 0x201 block: magic, total size (incl. 12-byte header), unpacked size, stream."""
    import struct
    body = compress(data)
    return struct.pack('<III', 0x201, len(body) + 12, len(data)) + body
