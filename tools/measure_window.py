"""창 줄바꿈 실측: 게임의 창 설정(0x800D328)과 대사 출력(0x800D4C0)을 롬 그대로 unicorn에서 돌려
글자를 그릴 때(0x800CD2C)마다 창 구조체(0x020127BC)의 칸(+6)·줄(+7)을 기록한다.

python tools/measure_window.py <롬> <대사 위치hex> <x> <y> <w> <h> [테두리=1]
- 입력 대기 {07}/{08}과 그 뒤는 잘라 낸다(입력을 기다리며 멈추므로). 글자 사이 지연(0x800CFC0)은 바로 돌아온다.
"""
import struct, sys
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED
from unicorn.arm_const import *

STOP = 0x08FFFFF0
WIN = 0x020127BC


def run(rom_path, text_off, x, y, w, h, frame=1, verbose=False):
    rom = open(rom_path, 'rb').read()
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    uc.mem_map(0x08000000, 0x01000000)
    uc.mem_write(0x08000000, rom)
    for base, size in ((0x02000000, 0x40000), (0x03000000, 0x8000), (0x04000000, 0x1000),
                       (0x05000000, 0x1000), (0x06000000, 0x20000), (0x07000000, 0x1000)):
        uc.mem_map(base, size)
    # 대사를 RAM에 복사: {07}/{08} 앞에서 자른다(바로 01 FE 같은 건너뛰기는 그대로 따라가게 롬을 읽는다)
    log = []

    def hook(u, addr, size, _):
        if addr == 0x0800CD2C:
            b = bytes(u.mem_read(WIN, 12))
            log.append((u.reg_read(UC_ARM_REG_R1), b[6], b[7], b[2], b[3], b[4]))
        elif addr == 0x0800CFC0 or addr == 0x0800D218:
            u.reg_write(UC_ARM_REG_R0, 0)
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))
        elif addr == STOP:
            u.emu_stop()
    uc.hook_add(UC_HOOK_CODE, hook)

    def bad(u, access, addr, size, value, _):
        print('맵 안 된 메모리', hex(addr), 'pc', hex(u.reg_read(UC_ARM_REG_PC)), 'lr', hex(u.reg_read(UC_ARM_REG_LR)))
        return False
    uc.hook_add(UC_HOOK_MEM_UNMAPPED, bad)

    def call(fn, regs, stack=()):
        sp = 0x03007E00 - 4 * len(stack)
        uc.mem_write(sp, b''.join(struct.pack('<I', v) for v in stack))
        uc.reg_write(UC_ARM_REG_SP, sp)
        for r, v in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), regs):
            uc.reg_write(r, v)
        uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        uc.emu_start(fn | 1, STOP, count=2_000_000)

    # 글꼴 문맥 초기화 구간(0x8004BF0~0x8004C54)만 돌린다
    uc.reg_write(UC_ARM_REG_SP, 0x03007E00)
    uc.emu_start(0x08004BF0 | 1, 0x08004C56, count=100000)
    call(0x0800D328, (x, y, w, h), (frame,))
    uc.mem_write(WIN + 0xC, struct.pack('<I', 0x030013B0))     # 글꼴 문맥(게임에서는 앞 창에서 이미 채워져 있음)
    # 대사: {07}/{08} 앞까지만 RAM에 옮긴다(건너뛰기 01 FE 는 롬 쪽 본문을 따라가며 같은 처리)
    p = text_off; out = bytearray()
    while True:
        b = rom[p]; p += 1
        if b == 0: break
        if b == 1:
            xx = rom[p]; p += 1
            if xx in (0xFE, 0xFD):
                p = struct.unpack_from('<I', rom, p)[0] - 0x08000000; continue
            if xx in (7, 8): break
            out += bytes([1, xx]); continue
        out.append(b)
        if b >= 0xF8: out.append(rom[p]); p += 1
    out.append(0)
    uc.mem_write(0x02030000, bytes(out))
    call(0x0800D4C0, (0x02030000,))
    return log


if __name__ == '__main__':
    a = sys.argv[1:]
    log = run(a[0], int(a[1], 16), *map(int, a[2:6]), *(map(int, a[6:7]) if len(a) > 6 else ()))
    for g, col, line, wid, lines, flag in log:
        print('글자 %4d  칸 %2d  줄 %d   (창 폭 %d, 줄 수 %d, 금칙 %d)' % (g, col, line, wid, lines, flag))
