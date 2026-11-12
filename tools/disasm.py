"""썸 디스어셈블: python disasm.py <롬오프셋hex> <바이트수hex>

capstone이 리터럴 자리 등 못 푸는 2바이트에서 멈추면 .hword 로 찍고 이어 간다.
"""
import sys, struct
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
d = open('Custom Robo GX (Japan).gba', 'rb').read()
o = int(sys.argv[1], 16); n = int(sys.argv[2], 16)
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
p, end = o, o + n
while p < end:
    last = p
    for i in md.disasm(d[p:end], 0x08000000 + p):
        extra = ''
        if i.mnemonic.startswith('ldr') and '[pc' in i.op_str:
            imm = int(i.op_str.split('#')[-1].rstrip(']'), 16) if '#' in i.op_str else 0
            a = ((i.address + 4) & ~3) + imm
            extra = '  ; =0x%08x' % struct.unpack_from('<I', d, a - 0x08000000)[0]
        print('%08x: %-8s %s%s' % (i.address, i.mnemonic, i.op_str, extra))
        last = i.address - 0x08000000 + i.size
    if last < end:
        print('%08x: .hword   0x%04x' % (0x08000000 + last, struct.unpack_from('<H', d, last)[0]))
        last += 2
    p = last
