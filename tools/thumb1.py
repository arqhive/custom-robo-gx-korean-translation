"""GBA(ARM7TDMI, ARMv4T)는 Thumb-1만 안다. keystone은 먼 조건 분기 등을 Thumb-2 32비트(beq.w 등)로 내므로 검사한다.
Thumb-1에서 32비트는 BL(F000~F7FF 다음 F800~FFFF)뿐이다."""
import struct


def bad_thumb2(code, base, end=None):
    """code[:end]를 Thumb-1로 읽어 BL이 아닌 32비트 명령 자리 목록을 돌려준다."""
    end = len(code) if end is None else end
    out, p = [], 0
    while p + 1 < end:
        h = struct.unpack_from('<H', code, p)[0]
        top = h >> 11
        if top == 0b11110 and p + 3 < len(code) and struct.unpack_from('<H', code, p + 2)[0] >> 11 == 0b11111:
            p += 4; continue
        if top in (0b11101, 0b11110, 0b11111):
            out.append(base + p)
        p += 2
    return out


def check(code, base, end=None, what=''):
    bad = bad_thumb2(code, base, end)
    assert not bad, '%s: GBA가 모르는 Thumb-2 명령 %s' % (what, ' '.join('%X' % a for a in bad))
    return code


def check_pool(code, base, what=''):
    """`ldr rX, =값` 리터럴 풀이 뒤에 붙은 코드: pc 상대 ldr이 가리키는 가장 앞 주소 전까지를 명령으로 보고 검사."""
    end, p = len(code), 0
    while p + 1 < end:
        h = struct.unpack_from('<H', code, p)[0]
        if h >> 11 == 0b01001:                                   # ldr rd, [pc, #imm8*4]
            end = min(end, ((base + p + 4) & ~3) + (h & 0xFF) * 4 - base)
        p += 2
    return check(code, base, end, what)
