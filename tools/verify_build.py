"""빌드 롬을 게임 리더와 같은 방식으로 다시 읽어 번역과 대조한다.

- 대사: 원래 자리에서 읽기 시작해 01 FE/FD/FC 를 따라가고, 00에서 끝난 다음 위치가 원래 끝+1인지(스크립트가 이어서 읽는 곳).
  글자는 새 글꼴 코드표·1바이트 표로 풀어 번역(줄바꿈 {05} 넣은 뒤, 자동 조사는 원래 괄호 꼴)과 같은지.
- 평문: 번역한 자리마다 참조 포인터를 따라가 읽은 문자열이 번역과 같은지(포인터 없는 자리는 그 자리).
- 비밀번호: 문자열 표에서 꺼내 XOR을 풀어 승인안과 같은지.
"""
import json, os, re, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
import build as Bd
import name_input as N
import script as S

rom = open(Bd.OUT, 'rb').read()
u32 = lambda o: struct.unpack_from('<I', rom, o)[0]


def font():
    lit = u32(0x4C84) - 0x08000000; cnt = struct.unpack_from('<H', rom, u32(0x4C90) - 0x08000000)[0]
    codes = struct.unpack_from('<%dH' % cnt, rom, lit)
    rev = {Bd.code_of(c): c for c in N.ORDER}
    ch = [None] + [rev.get(c) or bytes([c >> 8, c & 255]).decode('cp932') for c in codes]
    bm = struct.unpack_from('<248H', rom, Bd.BYTEMAP)
    return ch, bm


CH, BM = font()


def read_dialogue(p):
    out = []; hops = 0
    while True:
        b = rom[p]; p += 1
        if b == 0: return ''.join(out), p
        if b == 1:
            x = rom[p]; p += 1
            if x in (0xFE, 0xFD): p = u32(p) - 0x08000000; hops += 1; continue
            if x == 0xFC: p = u32(u32(0xD524) - 0x08000000 + 0) if False else SJ[rom[p]]; hops += 1; continue
            out.append('{%02X}' % x); continue
        if b <= 0xF7:
            v = BM[b]
            if 0xFFEF <= v < 0xFFEF + len(Bd.PARTICLES): out.append(Bd.PARTICLES[v - 0xFFEF][0]); continue
            if b == Bd.SPACE: out.append(' '); continue
            out.append(CH[v + 1])
        else:
            out.append(CH[(b - 0xF8) << 8 | rom[p]]); p += 1


def sj_table():
    """짧은 건너뛰기 표: 빌드가 남긴 build/layout.json 의 주소."""
    t = json.load(open(os.path.join(Bd.ROOT, 'build', 'layout.json')))['sjtab']
    return [u32(t + 4 * i) - 0x08000000 for i in range(256)]


SJ = sj_table()


def norm(t):
    return t.replace('　', ' ')


def main():
    global SMALLW, ORIG
    SMALLW = Bd.small_windows()
    ORIG = open(Bd.SRC, 'rb').read()
    jp2ko, raw, dlg = Bd.load()
    bad = 0; prev_end, prev_col = None, 0
    for e in sorted(dlg, key=lambda e: int(e['id'], 16)):
        off = int(e['id'], 16); n = e['bytes'] - 1; end = off + n
        tk = Bd.tokens(e['ko'])
        if e['kind'] == 'line':
            col0 = prev_col if prev_end is not None and 0 < off - prev_end <= 8 else 0
            if col0 and ORIG[prev_end] in (0x23, 0x25, 0x95): col0 = 0            # build.py와 같은 규칙(사이 명령 23 = 새 글)
            if col0 and 0x98 in ORIG[prev_end:off]: col0 = 0                # build.py와 같은 규칙(사이 98 = 창 비우기)
            tk, col = Bd.wrap(tk, SMALLW[off][0] if off in SMALLW else e['width'] - 1, col0)
            prev_col = col if not (tk and tk[-1][0] == 'k' and tk[-1][1] in (5, 6, 7)) else 0
        else: prev_col = 0
        prev_end = end + 1
        tk = Bd.drop_space_after_punct(tk)
        want =''.join('{%02X}' % v if k == 'k' else Bd.PARTICLES[v][0] if k == 'p' else Bd.dlg_char(v) if v not in Bd.SPACES else ' ' for k, v in tk)
        got, nxt = read_dialogue(off)
        got = re.sub(r'(\{04\})+$', '', got).rstrip(' ') if n < 6 or off in Bd.NO_JUMP else got
        want2 = re.sub(r'(\{04\})+$', '', want).rstrip(' ') if n < 6 or off in Bd.NO_JUMP else want
        if nxt != end + 1 or norm(got) != norm(want2):
            bad += 1
            if bad <= 10: print('대사 다름', e['id'], repr(got[:60]), repr(want2[:60]), hex(nxt), hex(end + 1))
    print('대사 대조', len(dlg), '다름', bad)
    allstr = json.load(open(os.path.join(Bd.TR, 'sjis-all.json'), encoding='utf-8'))
    info = {int(x['off'], 16): x for x in allstr['strings']}
    sbad = cnt = 0
    for x, ko in raw:
        want = Bd.sjis_bytes(Bd.raw_text(x, ko))
        for w in x['where']:
            o = int(w, 16)
            if any(a <= o < z for a, z in Bd.SKIP_RANGES): continue
            if o in info and any(g.split(':')[0] in '123' for g in info[o]['groups']):
                continue                                         # 키 겸용(키는 일본어 그대로, 화면 쪽은 묶음 표 칸을 옮김)
            refs = [int(r, 16) for r in info[o]['refs'] if Bd.real_ref(rom, int(r, 16))] if o in info else []
            if o in info and info[o]['refs'] and not refs:
                org = open(Bd.SRC, 'rb').read() if 'org' not in globals() else globals()['org']
                globals()['org'] = org
                if rom[o:o+len(want)+1] != want + bytes(1): continue      # 가짜 조각(빌드가 건너뜀)
            locs = [u32(r) - 0x08000000 for r in refs] if refs else [o]
            for a in set(locs):
                cnt += 1
                got = rom[a:rom.index(0, a)]
                if got != want:
                    sbad += 1
                    if sbad <= 10: print('평문 다름', x['id'], hex(o), hex(a), got[:20], want[:20])
    print('평문 대조', cnt, '다름', sbad)
    pbad = 0
    for sid, b in N.passwords().items():
        ent = u32(S.STR_GROUPS + 4 * (sid >> 12)) - 0x08000000 + 4 * (sid & 0xFFF)
        a = u32(ent) - 0x08000000
        if rom[a:a+len(b)] != b: pbad += 1
    print('비밀번호 대조', len(N.passwords()), '다름', pbad)
    return bad + sbad + pbad




def verify_gfx():
    """빌드 롬의 그림을 풀어 결과 PNG(원본 배율로 줄인 것)와 색이 같은지."""
    import build_gfx as BG, survey_gfx as G
    from lz77 import decode
    from PIL import Image
    def chunk(off, pal_before=0):
        refs = [o for o in range(0, 0x800000 - 3, 4) if struct.unpack_from('<I', BG.R, o)[0] == 0x08000000 + off]
        if refs: return u32(refs[0]) - 0x08000000
        if pal_before:
            v = off - pal_before - BG.ARCH_BASE
            ent = [BG.ARCH_TAB + 4 * i for i in range(4096) if struct.unpack_from("<I", BG.R, BG.ARCH_TAB + 4 * i)[0] == v]
            if not ent: return off   # 묶음 표에 없는 그림(접수처 등): 제자리에 들어갔어야 함(옮기면 build_gfx가 멈춤)
            ent = ent[0]
            return u32(ent) + BG.ARCH_BASE + pal_before
        return off
    bad = []
    def cmp(name, offs, w, h, wt, pals, layout, crop=None, pal_before=0):
        im = Image.open(os.path.join(BG.RES, name + '.png')).convert('RGB')
        cw, ch = crop or (max(x for x, _ in layout) + w, max(y for _, y in layout) + h)
        im = im.resize((cw, ch), Image.NEAREST)
        for i, off in enumerate(offs):
            a = chunk(off, pal_before)
            raw = decode(rom, a)[0]
            pb = pals[i] if isinstance(pals, list) else pals
            pal = G.full_pal(decode(BG.R, off)[0], 8, pb) if pb else G.gray_pal(256)
            idx = BG.tiles_to_idx(raw, 8, wt, w, h)
            x0, y0 = layout[i]
            for y in range(min(h, ch)):
                for x in range(min(w, cw)):
                    if pal[idx[y][x]] != im.getpixel((x0 + x, y0 + y)):
                        bad.append((name, i, x, y)); return
    R = BG.R
    for nm, offs in [('banner_junyusho', [0x369EB4, 0x36A2DC, 0x36A7D4]), ('banner_kessho', [0x36AC58, 0x36AF5C, 0x36B280]),
                     ('banner_yusho', [0x36B4D4, 0x36B884, 0x36BD50])]:
        cmp(nm, offs, 64, 64, 8, R[0x369DB4:0x369EB4], [(0, 0), (64, 0), (128, 0)])
    for o in [0x650004, 0x650A58, 0x652F30, 0x654AA8, 0x656D98, 0x659194, 0x65A6D4, 0x65DD28, 0x65F390, 0x668D04]:
        cmp('cup_%06X' % o, [o], 112, 80, 14, R[o - 0x100:o], [(0, 0)], pal_before=0x100)
    cmp('main_menu', [0x676F94], 240, 160, 30, BG.palof(0x676F94), [(0, 0)])
    cmp('league_table', [0x35D940], 240, 160, 30, R[0x39A194:0x39A394], [(0, 0)])
    cmp('scene_uketsuke', [0x5F5C6C], 240, 104, 30, R[0x5F5C6C - 0x100:0x5F5C6C], [(0, 0)], pal_before=0x100)
    for nm, offs in [('btn_taisen', [0x6768C8, 0x676C0C]), ('btn_option', [0x6794D4, 0x679818]),
                     ('btn_scenario', [0x679BDC, 0x679F3C]), ('btn_vs', [0x67A328, 0x67A67C])]:
        cmp(nm, offs, 128, 16, 16, [BG.palof(o) or BG.palof(offs[0]) for o in offs], [(0, 0), (0, 18)])
    for nm, o in [('face_fudan', 0x54C724), ('face_sento', 0x54C940), ('face_make', 0x54CB58)]:
        cmp(nm, [o], 64, 64, 8, BG.palof(o), [(0, 0)], crop=(48, 48))
    # 타이틀: 맵으로 합성해 색인 PNG와 대조
    t = chunk(0x352BB8); raw = decode(rom, t)[0]
    mp = struct.unpack('<600H', rom[0x355388:0x355388 + 1200])
    src = Image.open(os.path.join(BG.RES, 'title_logo.png')).convert('RGB').resize((240, 160), Image.NEAREST).load()
    tpal = [G.bgr(v & 0x7FFF) for v in struct.unpack('<240H', BG.R[0x3551A8:0x3551A8 + 480])] + [(0, 0, 0)] * 16
    for i, e in enumerate(mp):
        ti, hf, vf = e & 0x3FF, e >> 10 & 1, e >> 11 & 1
        for y in range(8):
            for x in range(8):
                sx = 7 - x if hf else x; sy = 7 - y if vf else y
                if tpal[raw[ti * 64 + sy * 8 + sx]] != src[(i % 30) * 8 + x, (i // 30) * 8 + y]:
                    bad.append(('title_logo', i)); break
            else: continue
            break
    print('그림 대조 25장, 다른 것', bad[:5] if bad else 0, '타이틀 타일', len(raw) // 64)
    return len(bad)


if __name__ == '__main__':
    sys.exit(1 if main() + verify_gfx() else 0)
