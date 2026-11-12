"""시나리오 대사 인코딩(글꼴 A 글자 번호) 디코더.
00=끝, 01 xx=제어, 02~F7=표 0x3F63AA 거쳐 글자 번호, F8~FF xx=글자 번호 직접((b-F8)<<8|xx)."""
import struct
ROM = 'Custom Robo GX (Japan).gba'
d = open(ROM, 'rb').read()
NGLYPH = 0x6B6
CODES = [struct.unpack_from('<H', d, 0x3F543E + 2*i)[0] for i in range(NGLYPH)]
CH = [bytes([c >> 8, c & 255]).decode('cp932', 'replace') for c in CODES]
BYTEMAP = [struct.unpack_from('<H', d, 0x3F63AA + 2*i)[0] for i in range(0xF8)]

def glyph_char(gi):
    # 0x800cd2c 는 1부터 세는 번호를 받는 것으로 보임(표 값+1)
    return CH[gi - 1] if 1 <= gi <= NGLYPH else None

def decode(buf, p, maxlen=4000):
    """p부터 00까지 해석. (문자열, 끝 다음 위치, 올바른지)"""
    out = []; s = p
    while p < len(buf) - 1 and p - s < maxlen:
        b = buf[p]; p += 1
        if b == 0: return ''.join(out), p, True
        if b == 1:
            x = buf[p]; p += 1
            out.append('{%02X}' % x); continue
        if b <= 0xF7:
            v = BYTEMAP[b]
            if v == 0xFFFF: return ''.join(out), p, False
            c = glyph_char(v + 1)  # 표 값은 0부터
        else:
            c = glyph_char((b - 0xF8) << 8 | buf[p]); p += 1  # 2바이트는 1부터 세는 번호
        if c is None: return ''.join(out), p, False
        out.append(c)
    return ''.join(out), p, False
