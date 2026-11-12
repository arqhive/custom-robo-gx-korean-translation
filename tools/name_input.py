"""한글 이름 입력: 자모 격자 + 두벌식 조합(이름 버퍼의 마지막 글자만 보고 조합, 상태 없음).

한글 고정 코드(평문 SJIS 문자열·이름 버퍼·글꼴 코드 표에 같이 쓴다):
- 순서 파일 work/font/hangul_order.txt 의 i번째 글자 → 코드 (0x88 + i//188, 0x40 + i%188, 0x7F 건너뜀).
  0x88~0x94는 SJIS 2바이트 첫 바이트 범위라 게임 리더(0x3D6088 표)가 2바이트로 읽는다.
- 순서: 번역에 쓰인 한글(유니코드 순) → 호환 자모 51자 → 나머지 KS X 1001 완성형(유니코드 순).
  글꼴 글리프 번호 = 정렬된 코드 순서라, 대사(2바이트 글리프 번호 ≤ 0x7FF)에 쓰는 글자가 앞에 온다.
- 순서 파일은 한 번 만들면 고정한다(이름이 세이브에 코드로 저장되므로 버전이 바뀌어도 같은 코드).
  새 글자는 끝에만 붙인다(--add).

조합 루틴(썸): 0x80151E2(격자에서 A를 눌렀고 칸 종류가 글자일 때, 원래는 길이 검사+strcat)를
`ldr r0,[pc,#4]; bx r0; nop; .word 루틴|1` 로 바꿔 루틴으로 뛴다.
들어올 때 r4=지금 글자 수, r5=입력 상태 구조체(+0x10 버퍼, +0x14 최대 글자 수), r6=칸(앞 2바이트가 글자 코드).
성공하면 0x80151FA(r7=1, 입력 효과음), 꽉 차서 못 넣으면 r7=0으로 0x80152A2(오류 효과음)로 돌아간다.
"""
import json, os, struct, sys
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDER_FILE = os.path.join(ROOT, 'work/font/hangul_order.txt')

KS = [bytes([a, b]).decode('euc_kr') for a in range(0xB0, 0xC9) for b in range(0xA1, 0xFF)]
assert len(KS) == 2350
JAMO = [chr(c) for c in range(0x3131, 0x3164)]   # 51
L_LIST = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'
V_LIST = 'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ'
T_LIST = ' ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ'
VCOMB = {('ㅗ', 'ㅏ'): 'ㅘ', ('ㅗ', 'ㅐ'): 'ㅙ', ('ㅗ', 'ㅣ'): 'ㅚ', ('ㅜ', 'ㅓ'): 'ㅝ', ('ㅜ', 'ㅔ'): 'ㅞ', ('ㅜ', 'ㅣ'): 'ㅟ', ('ㅡ', 'ㅣ'): 'ㅢ'}
TCOMB = {('ㄱ', 'ㅅ'): 'ㄳ', ('ㄴ', 'ㅈ'): 'ㄵ', ('ㄴ', 'ㅎ'): 'ㄶ', ('ㄹ', 'ㄱ'): 'ㄺ', ('ㄹ', 'ㅁ'): 'ㄻ', ('ㄹ', 'ㅂ'): 'ㄼ',
         ('ㄹ', 'ㅅ'): 'ㄽ', ('ㄹ', 'ㅌ'): 'ㄾ', ('ㄹ', 'ㅍ'): 'ㄿ', ('ㄹ', 'ㅎ'): 'ㅀ', ('ㅂ', 'ㅅ'): 'ㅄ'}
# 겹받침 → (남는 받침, 다음 글자로 넘어가는 자음)
TSPLIT = {'ㄳ': ('ㄱ', 'ㅅ'), 'ㄵ': ('ㄴ', 'ㅈ'), 'ㄶ': ('ㄴ', 'ㅎ'), 'ㄺ': ('ㄹ', 'ㄱ'), 'ㄻ': ('ㄹ', 'ㅁ'), 'ㄼ': ('ㄹ', 'ㅂ'),
          'ㄽ': ('ㄹ', 'ㅅ'), 'ㄾ': ('ㄹ', 'ㅌ'), 'ㄿ': ('ㄹ', 'ㅍ'), 'ㅀ': ('ㄹ', 'ㅎ'), 'ㅄ': ('ㅂ', 'ㅅ')}

HOOK = 0x080151E2
RET_OK = 0x080151FA
RET_FULL = 0x080152A2
LEAD0 = 0x88
PER_LEAD = 188


# ---------------------------------------------------------------- 고정 코드
def used_hangul():
    """번역 결과(제외 항목 빼고)에 쓰인 한글 음절."""
    import json, re
    O = os.path.join(ROOT, 'work/translation/out')
    ex = json.load(open(os.path.join(ROOT, 'work/translation/exclude.json'), encoding='utf-8'))
    s = set()
    for f in os.listdir(O):
        for k, v in json.load(open(os.path.join(O, f), encoding='utf-8'))['translations'].items():
            if k not in ex: s.update(c for c in re.sub(r'\{..\}', '', v) if '가' <= c <= '힣')
    return s


def make_order():
    used = sorted(used_hangul())
    rest = [c for c in KS if c not in set(used)]
    return used + JAMO + rest


def load_order():
    return open(ORDER_FILE, encoding='utf-8').read().split('\n')[0]


ORDER = load_order() if os.path.exists(ORDER_FILE) else None
IDX = {c: i for i, c in enumerate(ORDER)} if ORDER else {}


def idx2code(i):
    t = i % PER_LEAD
    trail = 0x40 + t + (1 if 0x40 + t >= 0x7F else 0)
    return bytes([LEAD0 + i // PER_LEAD, trail])


def code2idx(c):
    lead, trail = c[0], c[1]
    if not (LEAD0 <= lead < LEAD0 + 13) or trail < 0x40 or trail == 0x7F: return None
    i = (lead - LEAD0) * PER_LEAD + trail - 0x40 - (1 if trail > 0x7F else 0)
    return i if i < len(ORDER) else None


def code_of(ch):
    """한글·자모 → 고정 코드, 그 밖은 cp932."""
    if ch in IDX: return idx2code(IDX[ch])
    return ch.encode('cp932')


def decode_codes(raw):
    out, p = [], 0
    while p < len(raw) and raw[p]:
        if raw[p] >= 0x80 and not (0xA0 <= raw[p] < 0xE0):
            i = code2idx(raw[p:p+2])
            out.append(ORDER[i] if i is not None else raw[p:p+2].decode('cp932', 'replace')); p += 2
        else:
            out.append(chr(raw[p])); p += 1
    return out


# ---------------------------------------------------------------- 기준 구현(파이썬)
def compose_ref(buf, ch, maxlen):
    """buf: 글자 목록. 넣은 뒤 목록, 못 넣으면 None(꽉 참)."""
    buf = list(buf)

    def app(c):
        if len(buf) >= maxlen: return None
        return buf + [c]
    if ch not in JAMO or not buf: return app(ch)
    last = buf[-1]

    def enc(L, V, T):
        c = chr(0xAC00 + L * 588 + V * 28 + T); return c if c in IDX else None
    if '가' <= last <= '힣' and last in IDX:
        u = ord(last) - 0xAC00; L, V, T = u // 588, (u % 588) // 28, u % 28
        if ch not in V_LIST:
            if T == 0 and ch in T_LIST[1:]:
                r = enc(L, V, T_LIST.index(ch))
                if r: buf[-1] = r; return buf
            elif T and (T_LIST[T], ch) in TCOMB:
                r = enc(L, V, T_LIST.index(TCOMB[(T_LIST[T], ch)]))
                if r: buf[-1] = r; return buf
        else:
            v = V_LIST.index(ch)
            if T == 0:
                if (V_LIST[V], ch) in VCOMB:
                    r = enc(L, V_LIST.index(VCOMB[(V_LIST[V], ch)]), 0)
                    if r: buf[-1] = r; return buf
            else:
                keep, move = TSPLIT.get(T_LIST[T], (' ', T_LIST[T]))
                if move in L_LIST and len(buf) < maxlen:
                    r1 = enc(L, V, T_LIST.index(keep)); r2 = enc(L_LIST.index(move), v, 0)
                    if r1 and r2: buf[-1] = r1; buf.append(r2); return buf
    elif last in JAMO:
        if ch in V_LIST and last in L_LIST:
            r = enc(L_LIST.index(last), V_LIST.index(ch), 0)
            if r: buf[-1] = r; return buf
        if ch in V_LIST and last in V_LIST and (last, ch) in VCOMB:
            buf[-1] = VCOMB[(last, ch)]; return buf
    return app(ch)


# ---------------------------------------------------------------- 표
def tables():
    n = len(ORDER)
    dec = []
    for c in ORDER:
        if c in JAMO: dec.append(0x8000 | JAMO.index(c))
        else:
            u = ord(c) - 0xAC00; dec.append((u // 588) << 10 | ((u % 588) // 28) << 5 | u % 28)
    enc = [0] * 11172
    for i, c in enumerate(ORDER):
        if c not in JAMO: enc[ord(c) - 0xAC00] = i + 1
    jl = bytes([L_LIST.index(j) if j in L_LIST else 0xFF for j in JAMO])
    jv = bytes([V_LIST.index(j) if j in V_LIST else 0xFF for j in JAMO])
    jt = bytes([T_LIST.index(j) if j in T_LIST[1:] else 0 for j in JAMO])
    vc = bytearray(21 * 21)
    for (a, b), r in VCOMB.items(): vc[V_LIST.index(a) * 21 + V_LIST.index(b)] = V_LIST.index(r) + 1
    tc = bytearray(28 * 51)
    for (a, b), r in TCOMB.items(): tc[T_LIST.index(a) * 51 + JAMO.index(b)] = T_LIST.index(r)
    tkeep = bytearray(28); tmove = bytearray([0xFF] * 28)
    for t in range(1, 28):
        keep, move = TSPLIT.get(T_LIST[t], (' ', T_LIST[t]))
        tkeep[t] = T_LIST.index(keep)
        tmove[t] = L_LIST.index(move) if move in L_LIST else 0xFF
    vj = bytes([JAMO.index(v) for v in V_LIST])
    return [('dec', struct.pack('<%dH' % n, *dec)), ('enc', struct.pack('<11172H', *enc)),
            ('jl', jl), ('jv', jv), ('jt', jt), ('vc', bytes(vc)), ('tc', bytes(tc)),
            ('tkeep', bytes(tkeep)), ('tmove', bytes(tmove)), ('vj', vj)]


# ---------------------------------------------------------------- 썸 루틴
# 스택 칸: [sp+0]=입력 자모 번호 j, [sp+4]=L, [sp+8]=V, [sp+12]=T
ASM = '''
entry:
    ldrb r0, [r6]
    ldrb r1, [r6, #1]
    lsls r0, r0, #8
    orrs r0, r1
    mov  r7, r0               @ r7 = 입력 코드
    ldr  r6, [r5, #0x10]      @ r6 = 버퍼
    sub  sp, #16
    cmp  r4, #0
    beq  append
    bl   code2dec
    lsrs r1, r0, #8
    cmp  r1, #0x80
    bne  append               @ 자모가 아니면 그냥 붙임(위 바이트 0x80=자모, 0xFF=한글 아님)
    lsls r0, r0, #24
    lsrs r0, r0, #24
    str  r0, [sp]             @ j
    @ 마지막 글자
    lsls r0, r4, #1
    adds r0, r0, r6
    subs r0, #2
    ldrb r1, [r0, #1]
    ldrb r0, [r0]
    lsls r0, r0, #8
    orrs r0, r1
    bl   code2dec
    lsrs r1, r0, #8
    cmp  r1, #0x80
    beq  last_jamo
    lsrs r1, r0, #15
    bne  append               @ 한글 아님
    @ ---- 마지막이 음절: L,V,T
    lsrs r1, r0, #10
    str  r1, [sp, #4]
    lsls r1, r0, #22
    lsrs r1, r1, #27
    str  r1, [sp, #8]
    lsls r1, r0, #27
    lsrs r1, r1, #27
    str  r1, [sp, #12]
    ldr  r0, [sp]
    ldr  r1, t_jv
    ldrb r1, [r1, r0]         @ 입력 모음 번호(자음이면 0xFF)
    cmp  r1, #0xFF
    bne  syl_vowel
    @ 자음 입력
    ldr  r2, [sp, #12]
    cmp  r2, #0
    bne  syl_cons_T
    ldr  r1, t_jt
    ldrb r2, [r1, r0]         @ 받침 번호
    cmp  r2, #0
    beq  append
    b    try_replace_LV
syl_cons_T:
    movs r1, #51
    muls r1, r2, r1
    adds r1, r1, r0
    ldr  r2, t_tc
    ldrb r2, [r2, r1]         @ 겹받침
    cmp  r2, #0
    beq  append
try_replace_LV:
    ldr  r0, [sp, #4]
    ldr  r1, [sp, #8]
    bl   enc
    cmp  r0, #0
    beq  append
    b    replace
syl_vowel:
    ldr  r2, [sp, #12]
    cmp  r2, #0
    bne  syl_vowel_T
    @ 받침 없음: 겹모음
    ldr  r0, [sp, #8]
    movs r2, #21
    muls r2, r0, r2
    adds r2, r2, r1
    ldr  r0, t_vc
    ldrb r1, [r0, r2]
    cmp  r1, #0
    beq  append
    subs r1, #1
    ldr  r0, [sp, #4]
    movs r2, #0
    bl   enc
    cmp  r0, #0
    beq  append
    b    replace
syl_vowel_T:
    @ 받침이 다음 글자로 넘어감
    str  r1, [sp]             @ 이제 [sp] = 입력 모음 번호
    ldr  r0, t_tmove
    ldrb r0, [r0, r2]
    cmp  r0, #0xFF
    beq  append
    ldr  r3, [r5, #0x14]
    cmp  r4, r3
    bhs  full
    ldr  r1, [sp]
    movs r2, #0
    bl   enc                  @ 둘째 글자(넘어간 자음 + 모음)
    cmp  r0, #0
    beq  append
    mov  r7, r0               @ r7 = 둘째 글자 코드
    ldr  r2, [sp, #12]
    ldr  r0, t_tkeep
    ldrb r2, [r0, r2]
    ldr  r0, [sp, #4]
    ldr  r1, [sp, #8]
    bl   enc                  @ 첫 글자(남은 받침)
    cmp  r0, #0
    beq  append_cancel
    bl   put_last
    b    append
append_cancel:
    @ 첫 글자를 못 만들면 입력 자모를 그대로 붙임: r7을 다시 자모 코드로
    ldr  r0, [sp]
    ldr  r1, t_vj
    ldrb r0, [r1, r0]
    bl   jamo2code
    mov  r7, r0
    b    append
last_jamo:
    @ 마지막이 자모(r0 = 0x8000|jl)
    lsls r0, r0, #24
    lsrs r0, r0, #24          @ jl
    ldr  r1, [sp]
    ldr  r2, t_jv
    ldrb r1, [r2, r1]         @ 입력 모음 번호
    cmp  r1, #0xFF
    beq  append
    ldr  r2, t_jl
    ldrb r2, [r2, r0]
    cmp  r2, #0xFF
    beq  lj_vowel
    adds r0, r2, #0           @ L = 자음
    movs r2, #0
    bl   enc
    cmp  r0, #0
    beq  append
    b    replace
lj_vowel:
    ldr  r2, t_jv
    ldrb r2, [r2, r0]         @ 마지막 모음 번호
    cmp  r2, #0xFF
    beq  append
    movs r0, #21
    muls r2, r0, r2
    adds r2, r2, r1
    ldr  r0, t_vc
    ldrb r1, [r0, r2]
    cmp  r1, #0
    beq  append
    subs r1, #1
    ldr  r0, t_vj
    ldrb r0, [r0, r1]
    bl   jamo2code
replace:
    bl   put_last
    b    ok
append:
    ldr  r3, [r5, #0x14]
    cmp  r4, r3
    bhs  full
    lsls r0, r4, #1
    adds r0, r0, r6
    lsrs r1, r7, #8
    strb r1, [r0]
    strb r7, [r0, #1]
    movs r1, #0
    strb r1, [r0, #2]
    strb r1, [r0, #3]
ok:
    add  sp, #16
    ldr  r0, ret_ok
    bx   r0
full:
    add  sp, #16
    movs r7, #0
    ldr  r0, ret_full
    bx   r0

@ r0=코드 → 마지막 글자 자리에 씀
put_last:
    lsls r1, r4, #1
    adds r1, r1, r6
    subs r1, #2
    lsrs r2, r0, #8
    strb r2, [r1]
    strb r0, [r1, #1]
    bx   lr

@ r0=코드 → r0=dec 값(없으면 0xFFFF)
code2dec:
    lsrs r1, r0, #8           @ lead
    subs r1, #LEAD0
    cmp  r1, #13
    bhs  c2d_none
    lsls r2, r0, #24
    lsrs r2, r2, #24          @ trail
    cmp  r2, #0x40
    blo  c2d_none
    cmp  r2, #0x7F
    beq  c2d_none
    blo  c2d_lo
    subs r2, #1
c2d_lo:
    subs r2, #0x40
    movs r3, #PER_LEAD
    muls r1, r3, r1
    adds r1, r1, r2           @ idx
    ldr  r3, n_order
    cmp  r1, r3
    bhs  c2d_none
    lsls r1, r1, #1
    ldr  r3, t_dec
    ldrh r0, [r3, r1]
    bx   lr
c2d_none:
    ldr  r0, ffff
    bx   lr

@ r0=L, r1=V, r2=T → r0=코드(없으면 0)
enc:
    movs r3, #28
    muls r1, r3, r1
    adds r2, r2, r1
    ldr  r3, n588
    muls r0, r3, r0
    adds r0, r0, r2
    lsls r0, r0, #1
    ldr  r3, t_enc
    ldrh r0, [r3, r0]
    cmp  r0, #0
    beq  enc_ret
    subs r0, #1
    b    idx2code
enc_ret:
    bx   lr

@ r0=자모 번호 j → r0=코드
jamo2code:
    adds r0, #JAMO_BASE_LO
    ldr  r1, jamo_base_hi
    adds r0, r0, r1
@ r0=idx → r0=코드
idx2code:
    movs r1, #LEAD0
i2c_loop:
    cmp  r0, #PER_LEAD
    blo  i2c_done
    subs r0, #PER_LEAD
    adds r1, #1
    b    i2c_loop
i2c_done:
    adds r0, #0x40
    cmp  r0, #0x7F
    blo  i2c_ok
    adds r0, #1
i2c_ok:
    lsls r1, r1, #8
    orrs r0, r1
    bx   lr

    .align 2
ret_ok:   .word RET_OK_ADDR
ret_full: .word RET_FULL_ADDR
n_order:  .word N_ORDER
ffff:     .word 0xFFFF
n588:     .word 588
jamo_base_hi: .word JAMO_BASE_HI
'''


def module(base):
    """루틴+표를 base에 놓은 바이트와 진입 주소."""
    tb = tables()
    names = ['t_' + k for k, _ in tb]
    jbase = IDX[JAMO[0]]
    assert all(IDX[j] == jbase + k for k, j in enumerate(JAMO))
    src = ASM
    for k, v in {'RET_OK_ADDR': RET_OK | 1, 'RET_FULL_ADDR': RET_FULL | 1, 'N_ORDER': len(ORDER),
                 'JAMO_BASE_LO': jbase & 0xFF, 'JAMO_BASE_HI': jbase & ~0xFF, '#LEAD0': '#%d' % LEAD0,
                 '#PER_LEAD': '#%d' % PER_LEAD}.items():
        src = src.replace(k, str(v))
    src = '\n'.join(l.split('@')[0].rstrip() for l in src.split('\n'))   # 한글 주석은 keystone이 못 읽음
    ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
    # 표 주소는 코드 길이를 알아야 정해지므로 두 번 어셈블
    def build(addrs):
        lits = ''.join('%s: .word 0x%X\n' % (n, a) for n, a in zip(names, addrs))
        enc, _ = ks.asm(src + lits, base)
        return bytes(enc)
    code = build([0] * len(names))
    off = (len(code) + 3) & ~3
    addrs, blob = [], bytearray()
    for _, data in tb:
        addrs.append(base + off + len(blob)); blob += data; blob += bytes((-len(blob)) % 4)
    code2 = build(addrs)
    assert len(code2) == len(code)
    out = code2 + bytes(off - len(code2)) + bytes(blob)
    return out, base


def hook_bytes(entry):
    """0x80151E2에 쓸 점프(ldr r0,[pc,#4]; bx r0; nop; .word). 0x80151E2+4=0x80151E6 → 정렬 0x80151E4+4=0x80151E8."""
    return bytes.fromhex('0148 0047 c046'.replace(' ', '')) + struct.pack('<I', entry | 1)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--init':
        assert not os.path.exists(ORDER_FILE), '순서 파일이 이미 있음(고정). 새 글자는 --add'
        os.makedirs(os.path.dirname(ORDER_FILE), exist_ok=True)
        order = make_order()
        open(ORDER_FILE, 'w', encoding='utf-8').write(''.join(order) + '\n')
        print('순서 파일', len(order), '자')
    elif len(sys.argv) > 1 and sys.argv[1] == '--add':
        new = sorted(used_hangul() - set(ORDER))
        if new:
            open(ORDER_FILE, 'w', encoding='utf-8').write(ORDER + ''.join(new) + '\n')
        print('추가', ''.join(new))
    else:
        m, e = module(0x08F00000)
        print('모듈', len(m), '바이트, 순서', len(ORDER), '자, 자모 시작', IDX[JAMO[0]])


# ---------------------------------------------------------------- 격자(페이지) 데이터
PAGES = 0x7B6FDC          # 페이지 정보 12바이트 × 4: +0 칸 표 포인터, 칸 12바이트 × 66(11열 × 6줄, 11번째 열은 메뉴)
# 0 한글(원래 ひらがな), 2 영문, 3 숫자·기호. 1(カタカナ)은 어느 메뉴에서도 안 가게 해서 쓰지 않는다.
KO_GRID = ['ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊ', 'ㅋㅌㅍㅎㄲㄸㅃㅆㅉ　', 'ㅏㅑㅓㅕㅗㅛㅜㅠㅡㅣ', 'ㅐㅒㅔㅖㅘㅙㅚㅝㅞㅟ', 'ㅢ', '']
# 메뉴 열(줄 0~5): (글자, 종류, 가는 페이지). 종류 1=페이지 전환, 2=끝, 3=빈칸(커서가 건너뛰고 **다시 그리지 않음**)
# 빈칸은 그려지지 않아 앞 페이지 글자가 남으므로, 빈칸 줄(2·3·5)은 모든 페이지에서 같게 두고
# 이름은 원래처럼 4칸(「英文字　」)이 되게 전각 공백으로 채워 앞 페이지 이름을 덮는다.
MENU = {0: [('영문　　', 1, 2), ('숫자　　', 1, 3), ('', 3, 0), ('', 3, 0), ('끝　　　', 2, 0), ('', 3, 0)],
        2: [('한글　　', 1, 0), ('숫자　　', 1, 3), ('', 3, 0), ('', 3, 0), ('끝　　　', 2, 0), ('', 3, 0)],
        3: [('한글　　', 1, 0), ('영문　　', 1, 2), ('', 3, 0), ('', 3, 0), ('끝　　　', 2, 0), ('', 3, 0)]}


def cell(old, text, kind, page=0):
    """원래 칸(12바이트: +0 글자 9바이트, +9 가로 위치, +0xA 16비트)의 위치 비트는 두고 글자·종류(+0xA 6~8비트)·가는 페이지(+0xB 1~3비트)만 바꾼다."""
    s = b''.join(code_of(c) for c in text)
    assert len(s) <= 8, text
    v = struct.unpack_from('<H', old, 10)[0]
    v = (v & ~0x01C0 & ~0x0E00) | kind << 6 | page << 9
    return s + bytes(9 - len(s)) + old[9:10] + struct.pack('<H', v)   # +9 = 가로 위치


def patch_grid(rom):
    for p in (0, 2, 3):
        base = struct.unpack_from('<I', rom, PAGES + 12 * p)[0] - 0x08000000
        for r in range(6):
            for c in range(11):
                o = base + (r * 11 + c) * 12
                old = bytes(rom[o:o+12])
                if c == 10:
                    t, k, pg = MENU[p][r]
                    if t == '' and k == 3: t = '　'
                    new = cell(old, t, k, pg)
                elif p == 0:
                    # 빈 자리도 그려지는 공백 칸(종류 0)으로: 종류 3은 안 그려져 영문·숫자 페이지 글자가 남음
                    ch = KO_GRID[r][c] if c < len(KO_GRID[r]) else '　'
                    new = cell(old, ch, 0)
                else:
                    continue                      # 영문·숫자 페이지 글자 칸은 원래대로
                rom[o:o+12] = new


def patch(rom, base):
    """롬(bytearray)에 조합 루틴(base), 0x80151E2 점프, 격자를 넣는다. 글꼴·순서 코드는 빌드가 맞춘다."""
    m, entry = module(base)
    o = base - 0x08000000
    assert all(b == 0xFF for b in rom[o:o+len(m)]) or all(b == 0 for b in rom[o:o+len(m)]), '루틴 자리가 비어 있지 않음'
    rom[o:o+len(m)] = m
    h = HOOK - 0x08000000
    assert rom[h:h+2] == bytes.fromhex('6869'), '0x80151E2 원래 명령(ldr r0,[r5,#0x14])이 아님'
    rom[h:h+10] = hook_bytes(entry)
    patch_grid(rom)
    return len(m)


# ---------------------------------------------------------------- 레이디 P 비밀번호(XOR 감춤 문자열)
# 문자열 표 항목 첫 바이트가 FF면 뒤 바이트 쌍을 0x3F·0x7E로 XOR한 SJIS(0x800A664 → 0x800A630).
PASSWORD_FILE = os.path.join(ROOT, 'work/translation/password-proposed.json')


def hidden_bytes(text):
    raw = b''.join(code_of(c) for c in text)
    assert len(raw) % 2 == 0 and b'\0' not in raw, text
    return b'\xff' + bytes(b ^ (0x3F if i % 2 == 0 else 0x7E) for i, b in enumerate(raw)) + b'\0'


def unhide(raw):
    """게임 복호(0x800A630)와 같은 방식."""
    out, p = bytearray(), 1
    while raw[p]:
        out += bytes([raw[p] ^ 0x3F, raw[p+1] ^ 0x7E]); p += 2
    return out


def passwords():
    """{문자열 ID: 넣을 바이트} — 승인된 비밀번호(10/23)."""
    return {int(x['sid'], 16): hidden_bytes(x['after'])
            for x in json.load(open(PASSWORD_FILE, encoding='utf-8'))['passwords']}
