"""조합 루틴(썸)을 unicorn으로 돌려 파이썬 기준 구현(compose_ref)과 대조한다."""
import os, random, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import *
import name_input as N

BASE = 0x08F00000
STATE, BUF, CELL, STACK = 0x02001000, 0x02002000, 0x02003000, 0x03007F00
mod, entry = N.module(BASE)


def new_cpu():
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    uc.mem_map(0x08000000, 0x01000000)
    uc.mem_map(0x02000000, 0x40000)
    uc.mem_map(0x03000000, 0x8000)
    uc.mem_write(BASE, mod)
    stop = {N.RET_OK: 'ok', N.RET_FULL: 'full'}

    def hook(u, addr, size, res):
        if addr in stop: res.append(stop[addr]); u.emu_stop()
    return uc, hook


def run(seq, maxlen):
    """seq 글자를 차례로 넣고 화면 버퍼 글자 목록(그리고 꽉 참 횟수)을 돌려준다."""
    uc, hook = new_cpu()
    res = []
    uc.hook_add(UC_HOOK_CODE, hook, res)
    uc.mem_write(STATE + 0x10, struct.pack('<II', BUF, maxlen))
    uc.mem_write(BUF, bytes(0x20))
    fulls = 0
    for ch in seq:
        raw = bytes(uc.mem_read(BUF, 0x20))
        n = len(N.decode_codes(raw))
        uc.mem_write(CELL, N.code_of(ch) + b'\0')
        uc.reg_write(UC_ARM_REG_R4, n); uc.reg_write(UC_ARM_REG_R5, STATE); uc.reg_write(UC_ARM_REG_R6, CELL)
        uc.reg_write(UC_ARM_REG_R7, 0); uc.reg_write(UC_ARM_REG_SP, STACK)
        res.clear()
        uc.emu_start(entry | 1, 0x08FFFFFF, count=20000)
        assert res, ('멈추지 않음', seq, ch)
        assert uc.reg_read(UC_ARM_REG_SP) == STACK, '스택 어긋남'
        if res[0] == 'full':
            assert uc.reg_read(UC_ARM_REG_R7) == 0, '꽉 참 쪽은 r7=0(원래 코드가 r7을 돌려줌), 성공 쪽은 원래 코드가 r7=1로 덮음'
            fulls += 1
    return N.decode_codes(bytes(uc.mem_read(BUF, 0x20))), fulls


def ref(seq, maxlen):
    b, fulls = [], 0
    for ch in seq:
        r = N.compose_ref(b, ch, maxlen)
        if r is None: fulls += 1
        else: b = r
    return b, fulls


CASES = ['ㅎㅏㅇㅑㅌㅗ', 'ㄱㅏㅂㅅ', 'ㄱㅏㅂㅅㅣ', 'ㄷㅏㄹㄱㅏ', 'ㅇㅗㅏ', 'ㅁㅜㅓㅅ', 'ㅇㅡㅣㅅㅏ', 'ㅅㅏㄹㅁ', 'ㅏㅣ', 'ㅗㅏ',
         'ㄲㅗㅊ', 'ㄱㅣㅁㅊㅣ', 'ㅍㅏㄹㅂㅏㅇ', 'ㄴㅏㅎㅇㅏ', 'ＡＢㄱㅏ', 'ㅂㅂㅂㅂㅂㅂㅂㅂ', 'ㄱㅏㄱㅏㄱㅏㄱㅏㄱㅏㄱㅏㄱㅏ',
         'ㄱㅏㄱㅏㄱㅏㄱㅏㄱㅏㄱㅏㄴㅏ', 'ㅆㅑㄹ', 'ㅎㅑㅅ', 'ㅌㅗㅇ', 'ㅍㅜㅇ', 'ㅎㅚ', 'ㅌㅢ', 'ㄹㅔㅇㅣㅅㅡㅋㅏㅇㅣㅇㅓ',
         'ㅋㅓㅅㅡㅌㅓㅁ　ㄹㅗㅂㅗ', 'ㅇㅠㅇㅜㅅㅡㅋㅔ', 'ㄷㅗㄹ', 'ㄸㅗㅁ', 'ㄱㅏㄸ', 'ㅇㅏㄴㅈㅇㅏ', 'ㅇㅓㅄㅇㅓ', '１２ㄱ']
for maxlen in (7, 8):
    for c in CASES:
        got, ref_ = run(c, maxlen), ref(c, maxlen)
        assert got == ref_, (c, maxlen, got, ref_)
        if maxlen == 7: print('%-16s → %s%s' % (c, ''.join(got[0]), '  (꽉 참 %d)' % got[1] if got[1] else ''))
random.seed(1)
pool = N.JAMO + list('ＡＺ１　')
for k in range(3000):
    seq = [random.choice(pool) for _ in range(random.randint(1, 14))]
    ml = random.choice((1, 2, 7, 8))
    got, ref_ = run(seq, ml), ref(seq, ml)
    assert got == ref_, (''.join(seq), ml, got, ref_)
print('무작위 3000개 일치')
