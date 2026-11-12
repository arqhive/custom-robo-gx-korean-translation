"""시나리오 스크립트 해석.

- 묶음 시작 BANK=0x4B5FA0. 라벨 이름 표 0x3E42A0(포인터 260개), 오프셋 표 0x3E46B0(묶음 시작 기준).
- 인터프리터 0x8011EB8, 분기표 0x8011F08. 명령 1바이트, `01 xx`는 0x100+xx(피연산자 없음).
- 피연산자 길이(처리 함수에서 스크립트 포인터 0x0200C1A0+0xC28을 읽는 양, tools/opcode_lengths.py + 디스어셈블로 확인):
  02·0C·0D·2E·2F=1, 03·05~0B·2A~2D=2, 04=4, 23·24·26·27·29=3(상대 주소, 피연산자 끝 기준 부호 있는 24비트),
  99=대사 문자열(00까지, F8~FF xx와 01 xx는 두 바이트 글자), 나머지 0.
- 05 xx xx: SJIS 문자열 번호(상위 4비트=묶음, 하위 12비트=번호, 표 0x3E4268).
"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(__file__))
import gxtext as g

d = g.d
BANK = 0x4B5FA0
LABEL_NAMES = 0x3E42A0
LABEL_OFFS = 0x3E46B0
NLABEL = 0x104
LEN = {0x02: 1, 0x0C: 1, 0x0D: 1, 0x2E: 1, 0x2F: 1, 0x04: 4,
       0x23: 3, 0x24: 3, 0x26: 3, 0x27: 3, 0x29: 3}
for _o in (0x03, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x2A, 0x2B, 0x2C, 0x2D):
    LEN[_o] = 2
REL = {0x23, 0x24, 0x26, 0x27, 0x29}
STR_GROUPS = 0x3E4268


def u32(o): return struct.unpack_from('<I', d, o)[0]


def labels():
    out = []
    for i in range(NLABEL):
        name_ptr = u32(LABEL_NAMES + 4 * i) - 0x08000000
        name = d[name_ptr:d.index(0, name_ptr)].decode('cp932', 'replace')
        out.append((name, BANK + u32(LABEL_OFFS + 4 * i)))
    return out


def string_end(p):
    """대사 문자열 끝(00 다음) 위치."""
    while True:
        b = d[p]; p += 1
        if b == 0: return p
        if b == 1 or b >= 0xF8: p += 1


def sjis_string(sid):
    grp = u32(STR_GROUPS + 4 * (sid >> 12)) - 0x08000000
    ptr = u32(grp + 4 * (sid & 0xFFF)) - 0x08000000
    return ptr


def walk(start, end):
    """start~end 를 명령 단위로 걸음. [(위치, 명령, 피연산자 bytes, 부가)]"""
    ins = []; p = start
    while p < end:
        op = d[p]; q = p + 1
        if op == 1:
            op = 0x100 | d[q]; q += 1
            if op > 0x117: raise ValueError('잘못된 확장 명령 %X @%X' % (op, p))
        elif op == 0x99:
            q = string_end(q)
        else:
            q += LEN.get(op, 0)
        extra = None
        if op in REL:
            v = d[p+1] | d[p+2] << 8 | d[p+3] << 16
            if v & 0x800000: v -= 0x1000000
            extra = q + v
        ins.append((p, op, q - p, extra))
        p = q
    return ins


if __name__ == '__main__':
    ls = labels()
    print('라벨', len(ls), '오프셋 범위', hex(min(a for _, a in ls)), hex(max(a for _, a in ls)))


STOP_OPS = {0x00, 0x23, 0x25, 0x4B}   # 다음 명령으로 흐르지 않음


def decode_one(p):
    op = d[p]; q = p + 1
    if op == 1:
        op = 0x100 | d[q]; q += 1
        if op > 0x117: raise ValueError('잘못된 확장 명령 %X @%X' % (op, p))
    elif op == 0x99:
        q = string_end(q)
    else:
        q += LEN.get(op, 0)
    tgt = None
    if op in REL:
        v = d[p+1] | d[p+2] << 8 | d[p+3] << 16
        if v & 0x800000: v -= 0x1000000
        tgt = q + v
    return op, q, tgt


def trace(extra_starts=()):
    """시작 지점(묶음 시작·라벨)에서 흐름을 따라 닿는 명령 전부. {위치: (명령, 길이, 목적지)}"""
    starts = [BANK] + [a for _, a in labels()] + list(extra_starts)
    seen = {}; work = list(starts)
    while work:
        p = work.pop()
        while p not in seen:
            op, q, tgt = decode_one(p)
            seen[p] = (op, q - p, tgt)
            if tgt is not None: work.append(tgt)
            if op in STOP_OPS: break
            p = q
    return seen
