#!/usr/bin/env python3
"""Create a PPF 3.0 patch (BIN image, no undo data, no block check): make_ppf.py orig patched out.ppf [description]"""
import struct, sys

def make(orig, new, out, desc='SMT if... English patch'):
    a = open(orig, 'rb'); b = open(new, 'rb')
    recs = bytearray()
    off = 0
    CH = 1 << 20
    while True:
        x = a.read(CH); y = b.read(CH)
        if not y:
            break
        if len(x) != len(y):
            raise SystemExit('size mismatch')
        if x != y:
            i = 0
            n = len(y)
            while i < n:
                if x[i] == y[i]:
                    i += 1; continue
                j = i
                while j < n and j - i < 255 and x[j] != y[j]:
                    j += 1
                # merge short equal gaps to keep records few
                while j < n and j - i < 255:
                    k = j
                    while k < n and k - j < 8 and x[k] == y[k]:
                        k += 1
                    if k < n and k - j < 8 and x[k] != y[k]:
                        j = k
                        while j < n and j - i < 255 and x[j] != y[j]:
                            j += 1
                    else:
                        break
                j = min(j, i + 255)
                recs += struct.pack('<QB', off + i, j - i) + y[i:j]
                i = j
        off += len(y)
    hdr = b'PPF30' + bytes([2]) + desc.encode('ascii')[:50].ljust(50, b' ') + bytes([0, 0, 0, 0])
    open(out, 'wb').write(hdr + bytes(recs))

def apply(orig, ppf, out):
    data = bytearray(open(orig, 'rb').read())
    p = open(ppf, 'rb').read()
    assert p[:5] == b'PPF30'
    i = 60
    while i < len(p):
        o, n = struct.unpack_from('<QB', p, i); i += 9
        data[o:o + n] = p[i:i + n]; i += n
    open(out, 'wb').write(data)

if __name__ == '__main__':
    if sys.argv[1] == 'apply':
        apply(*sys.argv[2:5])
    else:
        make(*sys.argv[1:5])
