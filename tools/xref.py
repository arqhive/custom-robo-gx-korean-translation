"""썸 BL 호출·리터럴 참조 찾기: python xref.py <대상주소hex> [끝hex]"""
import sys, struct
d = open('Custom Robo GX (Japan).gba', 'rb').read()
CODE_END = 0x60000
def bl_targets():
    for o in range(0, CODE_END - 4, 2):
        h1 = d[o] | d[o+1] << 8; h2 = d[o+2] | d[o+3] << 8
        if (h1 & 0xF800) == 0xF000 and (h2 & 0xF800) == 0xF800:
            off = ((h1 & 0x7FF) << 12) | ((h2 & 0x7FF) << 1)
            if off & 0x400000: off -= 0x800000
            yield o, 0x08000000 + o + 4 + off
if __name__ == '__main__':
    t = int(sys.argv[1], 16); e = int(sys.argv[2], 16) if len(sys.argv) > 2 else t + 1
    for o, tg in bl_targets():
        if t <= tg < e: print('bl  %08x -> %08x' % (0x08000000 + o, tg))
    for o in range(0, len(d) - 4, 4):
        v = struct.unpack_from('<I', d, o)[0]
        if t <= v < e or t <= (v | 1) - 1 < e and v & 1 and t <= v - 1 < e:
            print('lit %08x = %08x' % (0x08000000 + o, v))
