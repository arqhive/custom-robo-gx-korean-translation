"""2단계 출력 시험 롬: 첫 장면 대사 몇 줄과 이름 입력 문구를 한글로 바꾼다.

- 한글 글리프: 갈무리11 Condensed 12px, 글꼴 A에서 거의 안 쓰는 한자 칸을 덮어쓴다.
- 대사: 원래 문자열 자리에 `01 FE <주소4>`를 쓰고 한글 문장은 롬 빈 공간에 둔다.
  한글 문장 끝의 `01 FD <주소4>`가 원래 문자열의 끝(00)으로 되돌린다.
  두 제어 코드는 대사 해석 함수 0x800D4C0의 `01 xx` 처리에 넣은 훅이 처리한다.
- 이름 입력 문구(평문 SJIS): 덮어쓴 칸의 SJIS 코드로 같은 자리에 쓴다.

python -X utf8 tools/build_probe.py  →  build/Custom Robo GX (Japan) [KO probe].gba
"""
import os, re, struct, sys, json, collections
from PIL import Image, ImageDraw, ImageFont
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
sys.path.insert(0, os.path.dirname(__file__))
import gxtext as g

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'Custom Robo GX (Japan).gba')
OUT = os.path.join(ROOT, 'build', 'Custom Robo GX (Japan) [KO probe].gba')
FONT = os.path.join(ROOT, 'tools', 'fonts', 'Galmuri11-Condensed.ttf')

GLYPHS = 0x3E7D5E          # 글리프 데이터(번호 0은 빈 칸, SJIS 코드 k → 글리프 k+1)
FREE = 0x7CC000            # 롬 끝 0xFF 빈 공간(0x7CAFB4~)
LOOP_TOP = 0x0800D4E0      # 다음 글자 읽기
SPACE_BYTE = 0x02          # 1바이트 02 → 전각 공백
OPEN, CLOSE = b'\xf8\x34', b'\xf8\x35'   # 「 」

# 첫 장면(엄마가 깨우는 장면). 키 = 문자열 시작(대사 명령 0x99 다음) 오프셋
DIALOGUE = {
    0x4B66D8: '「무, 무슨 일이니, {0A}」{07}',
    0x4B66EA: '「어머어머, 또 침대에서 굴러떨어지고…{08}또 {01}커스텀 로보{04} 꿈을 꿨나 보구나.」{07}',
    0x4B671F: '「자, 이제 슬슬 일어나렴. 오늘은 {02}생일{04}이잖니. {01}아빠{04}한테서 편지가 왔단다.」{07}',
    0x4B675B: '「편지만이 아니라 소포도!{08}　우후후.」{07}',
    0x4B677C: '「그럼 {01}거실{04}에서 기다릴게.」{07}',
    0x4B6820: '「정말!{08}　언제까지 잘 거니!」{07}',
    0x4B683D: '「{0A}!　적당히 좀 하렴.{08}침대에서 몇 번이나 떨어져야 직성이 풀리겠니?」{07}',
    0x4B686E: '「자, 어서 {01}거실{04}로 오렴.」{07}',
}
# 화자 이름(같은 자리, 같은 길이로): お母さん{05} 7바이트
SPEAKER = {0x4B66CF: ('엄마 {05}', 7)}

# 이름 입력 문구: 원문 → 한글(같은 자리, 원문 바이트 수 이하)
UI = {
    'なにか文字を入力して下さい': '뭔가 글자를 입력해 주세요',
    'でいいですか？': '로 괜찮아요?',
    'いいえ': '아니요',
    'はい': '예',
    'カタカナ': '가타카나',
    'ひらがな': '히라가나',
}
UI_RANGE = (0x7B6000, 0x7B8000)


def glyph_usage(d):
    """대사(시나리오 구역)와 평문 SJIS에서 글리프 번호별 사용 횟수."""
    use = collections.Counter()
    for o, t in json.load(open(os.path.join(ROOT, 'work', 'dialogue-scan.json'), encoding='utf-8')):
        for ch in re.sub(r'\{..\}', '', t):
            if ch in g.CH: use[g.CH.index(ch) + 1] += 1
    for ch in d[0x2F0000:0x330000].decode('cp932', 'ignore'):
        if ch in g.CH: use[g.CH.index(ch) + 1] += 1
    return use


def render(ch, font):
    im = Image.new('L', (8, 16))
    ImageDraw.Draw(im).text((0, 0), ch, font=font, fill=255)
    body = im.crop((0, 1, 8, 12)).point(lambda p: 255 if p > 127 else 0)
    cell = Image.new('L', (8, 16)); cell.paste(body, (0, 2))
    out = bytearray()
    for y in range(16):
        v = 0
        for x in range(8):
            if cell.getpixel((x, y)): v |= 3 << (2 * x)
        out += struct.pack('<H', v)
    return bytes(out)


def assemble(code, addr):
    ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
    enc, _ = ks.asm(code, addr)
    return bytes(enc)


def main():
    d = bytearray(open(SRC, 'rb').read())
    texts = list(DIALOGUE.values()) + [s for s, _ in SPEAKER.values()] + list(UI.values())
    need = sorted({c for t in texts for c in re.sub(r'\{..\}', '', t) if c not in '「」　 '})
    use = glyph_usage(d)
    kanji = [i + 1 for i, c in enumerate(g.CH) if '一' <= c <= '鿿']
    slots = sorted(kanji, key=lambda gi: (use[gi], -gi))[:len(need)]
    assert all(use[s] == 0 for s in slots), '안 쓰는 한자 칸이 모자람'
    font = ImageFont.truetype(FONT, 12)
    slot_of = {}
    for ch, gi in zip(need, slots):
        d[GLYPHS + gi * 32: GLYPHS + gi * 32 + 32] = render(ch, font)
        slot_of[ch] = gi

    def enc_dialogue(t):
        out = bytearray(); i = 0
        while i < len(t):
            if t[i] == '{':
                out += bytes([1, int(t[i+1:i+3], 16)]); i += 4; continue
            c = t[i]; i += 1
            if c == '「': out += OPEN
            elif c == '」': out += CLOSE
            elif c in ' 　': out.append(SPACE_BYTE)
            else:
                gi = slot_of[c]; out += bytes([0xF8 + (gi >> 8), gi & 0xFF])
        return bytes(out)

    # 훅: `01 xx`에서 xx>0x0A 분기(0x800D520: adds r0,r5,#0 / bl 0x800CD7C / b 루프)를 바꾼다.
    # 여기 올 때 r1=xx, r4=xx 다음. FE·FD면 다음 4바이트 주소로 r4를 옮기고 루프로,
    # 아니면 원래대로 0x800CD7C(r0=r5, r1=xx)를 부르고 루프로.
    hook_addr = 0x08000000 + FREE
    hook = assemble(f'''
        cmp r1, #0xFE
        beq jump
        cmp r1, #0xFD
        beq jump
        adds r0, r5, #0
        ldr r2, =0x0800CD7D
        bl veneer
        b back
    jump:
        ldrb r0, [r4]
        ldrb r2, [r4, #1]
        lsls r2, r2, #8
        orrs r0, r2
        ldrb r2, [r4, #2]
        lsls r2, r2, #16
        orrs r0, r2
        ldrb r2, [r4, #3]
        lsls r2, r2, #24
        orrs r0, r2
        adds r4, r0, #0
    back:
        ldr r0, =0x{LOOP_TOP | 1:08X}
        bx r0
    veneer:
        bx r2
    ''', hook_addr)
    d[FREE:FREE + len(hook)] = hook
    # 0x800D520: ldr r0,[pc,#0] / bx r0 / .word hook|1  (8바이트, 리터럴은 0x800D524에 정렬)
    patch = assemble('ldr r0, [pc, #0]\nbx r0', 0x0800D520) + struct.pack('<I', hook_addr | 1)
    assert len(patch) == 8 and d[0xD520:0xD528] == bytes.fromhex('28 1c ff f7 2b fc db e7'.replace(' ', ''))
    d[0xD520:0xD528] = patch

    p = (FREE + len(hook) + 3) & ~3
    report = []
    for off, t in DIALOGUE.items():
        end = d.index(0, off)
        assert end - off >= 6, hex(off)
        body = enc_dialogue(t) + b'\x01\xfd' + struct.pack('<I', 0x08000000 + end)
        d[p:p + len(body)] = body
        d[off:off + 6] = b'\x01\xfe' + struct.pack('<I', 0x08000000 + p)
        report.append((hex(off), end - off, len(body)))
        p += len(body)
    for off, (t, n) in SPEAKER.items():
        b = enc_dialogue(t)
        assert len(b) == n and d[off + n] == 0, (hex(off), len(b))
        d[off:off + n] = b

    def enc_sjis(t):
        out = bytearray()
        for c in t:
            if c == ' ': out.append(0x20)
            elif c in slot_of:
                code = g.CODES[slot_of[c] - 1]; out += bytes([code >> 8, code & 0xFF])
            else: out += c.encode('cp932')
        return bytes(out)
    ui_hits = 0
    for jp, ko in UI.items():
        src = jp.encode('cp932'); dst = enc_sjis(ko)
        assert len(dst) <= len(src), jp
        i = UI_RANGE[0]
        while True:
            i = d.find(src, i, UI_RANGE[1])
            if i < 0: break
            # 앞뒤가 문자열 경계(00)인 것만
            if d[i - 1] == 0 and d[i + len(src)] == 0:
                d[i:i + len(src)] = dst + b'\x00' * (len(src) - len(dst)); ui_hits += 1
            i += len(src)

    # 헤더 보정 바이트
    chk = (-(sum(d[0xA0:0xBD]) + 0x19)) & 0xFF
    d[0xBD] = chk
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, 'wb').write(d)
    print('한글 글자', len(need), '칸', slots[:5], '...')
    print('대사', report)
    print('UI 바꾼 곳', ui_hits, '빈 공간 사용 끝', hex(p))
    print('출력', OUT)


if __name__ == '__main__':
    main()
