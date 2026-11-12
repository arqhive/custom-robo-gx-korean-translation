"""스크립트 명령별 피연산자 길이를 에뮬레이터로 잰다.

인터프리터 0x8011EB8: 포인터 = [0x0200C1A0+0xC28], 명령 1바이트(01 xx 는 0x100+xx), 분기표 0x8011F08.
명령마다 처리 함수를 실행하고, 스크립트 버퍼에서 읽은 가장 먼 위치와 마지막 포인터 값을 기록한다.
버퍼는 0x02(공백 글자)로 채우고 FILL_END 에 00 을 둔다(문자열을 읽는 명령 구분용).

python -X utf8 tools/opcode_lengths.py  →  manifests/opcode-lengths.json
"""
import json, os, struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_MEM_READ, UC_HOOK_CODE, UC_HOOK_INTR, UcError
from unicorn.arm_const import *

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROM = open(os.path.join(ROOT, 'Custom Robo GX (Japan).gba'), 'rb').read()
BASE = 0x0200C1A0
PTR = BASE + 0xC28
TABLE = 0x11F08
LOOP = 0x08011EC6
BUF = 0x02038000
FILL_END = 0x40
STOP = 0x00001000          # 처리 함수가 인터프리터 밖으로 돌아가면 여기로


def run(op):
    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    for a, n in ((0, 0x4000), (0x02000000, 0x40000), (0x03000000, 0x8000), (0x04000000, 0x1000),
                 (0x05000000, 0x1000), (0x06000000, 0x18000), (0x07000000, 0x1000)):
        mu.mem_map(a, n)
    mu.mem_map(0x08000000, len(ROM)); mu.mem_write(0x08000000, ROM)
    buf = bytearray([0x02] * 0x100); buf[FILL_END] = 0
    mu.mem_write(BUF, bytes(buf))
    mu.mem_write(PTR, struct.pack('<I', BUF))
    # VM 스택(0x0200CC80, 개수 바이트 +0x40)에 값 8개를 넣어 둔다(꺼내는 명령이 오류로 빠지지 않게)
    mu.mem_write(0x0200CC80, struct.pack('<8I', *([1] * 8)))
    mu.mem_write(0x0200CCC0, bytes([8]))
    st = {'max': -1, 'n': 0}

    def on_read(uc, access, addr, size, value, ud):
        if BUF <= addr < BUF + 0x100:
            st['max'] = max(st['max'], addr + size - 1 - BUF)

    def on_code(uc, addr, size, ud):
        st['n'] += 1
        if addr in (LOOP, STOP, 0x080050A8) or st['n'] > 20000:
            uc.emu_stop()

    def on_intr(uc, intno, ud):   # BIOS 호출은 건너뜀
        pc = uc.reg_read(UC_ARM_REG_PC)

    mu.hook_add(UC_HOOK_MEM_READ, on_read)
    mu.hook_add(UC_HOOK_CODE, on_code)
    mu.hook_add(UC_HOOK_INTR, on_intr)
    sp = 0x03007E00 - 0x1A0
    mu.reg_write(UC_ARM_REG_SP, sp)
    mu.reg_write(UC_ARM_REG_R7, BASE)
    mu.reg_write(UC_ARM_REG_LR, STOP | 1)
    # 인터프리터 프레임 복귀 주소(스택) — 처리 함수가 함수를 빠져나가면 STOP 으로
    mu.mem_write(sp + 0x18C + 12, struct.pack('<I', STOP | 1) * 8)
    handler = struct.unpack_from('<I', ROM, TABLE + 4 * op)[0]
    err = None
    try:
        mu.emu_start(handler | 1, 0xFFFFFFFF, count=200000)
    except UcError as e:
        err = str(e)
    end = struct.unpack('<I', mu.mem_read(PTR, 4))[0]
    pc = mu.reg_read(UC_ARM_REG_PC)
    return {'op': op, 'handler': hex(handler), 'read_max': st['max'], 'ptr_adv': end - BUF,
            'stop': hex(pc), 'steps': st['n'], 'err': err}


def main():
    res = [run(op) for op in range(0x118)]
    os.makedirs(os.path.join(ROOT, 'manifests'), exist_ok=True)
    json.dump(res, open(os.path.join(ROOT, 'manifests', 'opcode-lengths.json'), 'w'), indent=1)
    for r in res:
        print('%03X %s 읽음%3d 전진%6d 멈춘곳 %s %s' % (r['op'], r['handler'], r['read_max'] + 1, r['ptr_adv'], r['stop'], r['err'] or ''))


if __name__ == '__main__':
    main()
