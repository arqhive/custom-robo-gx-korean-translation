"""GBA BIOS LZ77(0x10) 압축 풀기·찾기."""
def decode(d, off, limit=0x200000):
    if d[off] != 0x10: return None
    size = int.from_bytes(d[off+1:off+4], 'little')
    if size == 0 or size > limit: return None
    out = bytearray(); p = off + 4
    try:
        while len(out) < size:
            flags = d[p]; p += 1
            for i in range(8):
                if len(out) >= size: break
                if flags & 0x80:
                    b1, b2 = d[p], d[p+1]; p += 2
                    n = (b1 >> 4) + 3; disp = ((b1 & 0xF) << 8 | b2) + 1
                    if disp > len(out): return None
                    for _ in range(n): out.append(out[-disp])
                else:
                    out.append(d[p]); p += 1
                flags <<= 1
    except IndexError:
        return None
    return bytes(out[:size]), p - off
