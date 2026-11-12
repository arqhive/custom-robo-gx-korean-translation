"""그림 글씨 25장을 롬에 넣는다(build.py에서 부름). 24번째 리그 표·25번째 접수처 간판은 11/12 추가.

결과 PNG: work/graphics/hub/result/ (통합 폴더에서 복사, 원본 시트와 같은 배율: 대부분 2배, 얼굴 3배, 통신 메뉴 1배).
- 원래 데이터를 풀어 색 번호 그림을 만들고, 결과 PNG 픽셀 색이 원본과 같으면 원래 번호를 쓰고,
  다르면 팔레트에서 같은 색 번호를 찾는다(원본 그림에 쓰인 번호 먼저). 팔레트 밖 색이면 멈춘다.
- LZ77(거리 2 이상, VRAM 해제 안전)로 다시 압축해 원래 크기 안이면 제자리, 넘치면 새 공간에 두고 포인터를 바꾼다.
- 타이틀 로고는 맵(30×20)이 있어 칸마다 타일을 다시 짜고 맵을 제자리에 쓴다.
"""
import os, struct, sys
from PIL import Image
sys.path.insert(0, os.path.dirname(__file__))
import survey_gfx as G
from lz77 import decode

_HUB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'work', 'graphics', 'hub')
RES = os.path.join(_HUB, 'result')          # 그림 작업 통합 세션 결과 사본(10/30 복사, 원래 G:/KoreanTranslation/커스텀로보 그림글씨 결과/gx)
ORIG = os.path.join(_HUB, 'original')       # 원본 추출본 사본
R = G.ROM
ARCH_BASE, ARCH_TAB = 0x64C180, 0x3E5134


def lz_compress(data):
    out = bytearray([0x10]) + len(data).to_bytes(3, 'little')
    i, n = 0, len(data)
    while i < n:
        flag_pos = len(out); out.append(0); flags = 0
        for bit in range(8):
            if i >= n: break
            best_len, best_d = 0, 0
            lo = max(0, i - 4096)
            maxl = min(18, n - i)
            if maxl >= 3:
                j = data.rfind(data[i:i+3], lo, i - 1 + 3 - 1)    # 거리 ≥ 2
                while j >= lo:
                    if i - j >= 2:
                        l = 3
                        while l < maxl and data[j + l] == data[i + l]: l += 1
                        if l > best_len: best_len, best_d = l, i - j
                        if l == maxl: break
                    j = data.rfind(data[i:i+3], lo, j + 3 - 1)
            if best_len >= 3:
                flags |= 0x80 >> bit
                v = (best_len - 3) << 12 | (best_d - 1)
                out += bytes([v >> 8, v & 0xFF]); i += best_len
            else:
                out.append(data[i]); i += 1
        out[flag_pos] = flags
    while len(out) % 4: out.append(0)
    return bytes(out)


def to_index(new_rgb, old_idx, pal, name):
    """새 RGB 그림 → 색 번호. old_idx: 같은 크기 원래 번호 그림(2차원 목록)."""
    W, H = new_rgb.size
    px = new_rgb.load()
    import collections
    used = {old_idx[y][x] for y in range(H) for x in range(W)}
    # 같은 색이 팔레트 여러 칸에 있으면, 원본 그림에서 그 색에 실제로 가장 많이 쓴 번호를 고른다
    # (시트 팔레트와 게임이 실제로 쓰는 팔레트가 다를 수 있어서, 원본이 쓴 번호가 가장 안전)
    seen = collections.defaultdict(collections.Counter)
    for y in range(H):
        for x in range(W):
            seen[pal[old_idx[y][x]]][old_idx[y][x]] += 1
    cand = {}
    for c, cnt in seen.items():
        cand[c] = [k for k, _ in cnt.most_common()]
    for i, c in enumerate(pal):
        cand.setdefault(c, []).append(i)
    out = [[0] * W for _ in range(H)]
    miss = set()
    for y in range(H):
        for x in range(W):
            c = px[x, y][:3]; o = old_idx[y][x]
            if pal[o] == c: out[y][x] = o; continue
            ks = cand.get(c)
            if not ks: miss.add(c); continue
            pref = [k for k in ks if k in used]
            out[y][x] = (pref or ks)[0]
    assert not miss, (name, '팔레트 밖 색', list(miss)[:5])
    return out


def tiles_to_idx(data, bpp, wt, w, h):
    tsz = 64 if bpp == 8 else 32
    img = [[0] * w for _ in range(h)]
    for t in range(len(data) // tsz):
        tx, ty = (t % wt) * 8, (t // wt) * 8
        for y in range(8):
            for x in range(8):
                if tx + x >= w or ty + y >= h: continue
                if bpp == 8: c = data[t * tsz + y * 8 + x]
                else:
                    b = data[t * tsz + y * 4 + x // 2]; c = (b >> 4) if x & 1 else b & 15
                img[ty + y][tx + x] = c
    return img


def idx_to_tiles(img, data, bpp, wt):
    d = bytearray(data); tsz = 64 if bpp == 8 else 32
    h, w = len(img), len(img[0])
    for t in range(len(data) // tsz):
        tx, ty = (t % wt) * 8, (t // wt) * 8
        for y in range(8):
            for x in range(8):
                if tx + x >= w or ty + y >= h: continue
                c = img[ty + y][tx + x]
                if bpp == 8: d[t * tsz + y * 8 + x] = c
                else:
                    o = t * tsz + y * 4 + x // 2
                    d[o] = (d[o] & 0x0F) | c << 4 if x & 1 else (d[o] & 0xF0) | c
    return bytes(d)


def load_png(name, w, h):
    im = Image.open(os.path.join(RES, name + '.png'))
    sc = im.width // w
    assert im.width == w * sc and im.height == h * sc, (name, im.size, w, h)
    return im, sc


def put_lz(rom, alloc, off, raw, stat, pal_before=0):
    """LZ 덩어리 off 를 raw 로 바꾼다."""
    old = decode(R, off)
    assert old and len(old[0]) == len(raw), hex(off)
    clen = old[1]
    c = lz_compress(raw)
    assert decode(c, 0)[0] == raw
    if len(c) <= clen:
        rom[off:off+clen] = c + bytes(clen - len(c)); stat['제자리'] += 1; return
    refs = [o for o in range(0, 0x800000 - 3, 4) if struct.unpack_from('<I', R, o)[0] == 0x08000000 + off]
    if not refs and pal_before:
        # 대회 카드 등: 팔레트 = 0x864C180 + 표 0x3E5134[i], 그림 = 팔레트 + 0x100 (0x800E930)
        v = off - pal_before - ARCH_BASE
        ent = [ARCH_TAB + 4 * i for i in range(4096) if struct.unpack_from('<I', R, ARCH_TAB + 4 * i)[0] == v]
        assert len(ent) == 1, ('묶음 표 칸', hex(off), ent)
        a = alloc.put(R[off - pal_before:off] + c)
        struct.pack_into('<I', rom, ent[0], a - ARCH_BASE)
        stat['옮김(묶음 표)'] += 1
        return
    assert refs, ('옮겨야 하는데 포인터를 못 찾음', hex(off), len(c), clen)
    if pal_before:
        a = alloc.put(R[off - pal_before:off] + c) + pal_before
    else:
        a = alloc.put(c)
    for r in refs: struct.pack_into('<I', rom, r, 0x08000000 + a)
    stat['옮김'] += 1


def palof(o):
    import json
    idx = json.load(open(os.path.join(G.OUT, 'lz_index.json')))
    x = {e['off']: e for e in idx}[o]
    if 'pal' not in x: return None
    k, a, n = x['pal']
    return decode(R, a)[0] if k == 'lz' else R[a:a + n]


def simple(rom, alloc, stat, name, offs, w, h, wt, palbytes, layout, crop=None, pal_before=0):
    """offs 덩어리들을 layout[i]=(x, y) 자리에 놓인 w×h 그림으로 보고 교체."""
    W = max(x for x, _ in layout) + w; H = max(y for _, y in layout) + h
    im, sc = load_png(name, *(crop or (W, H)))
    im = im.convert('RGBA').resize((im.width // sc, im.height // sc), Image.NEAREST)
    for i, off in enumerate(offs):
        raw = decode(R, off)[0]
        pb = palbytes[i] if isinstance(palbytes, list) else palbytes
        pal = G.full_pal(raw, 8, pb) if pb else G.gray_pal(256)     # 팔레트 모르는 얼굴 칸은 조사 시트도 가짜 색으로 그림
        old = tiles_to_idx(raw, 8, wt, w, h)
        x0, y0 = layout[i]
        cw, ch = (crop or (w, h))
        part = im.crop((x0, y0, x0 + min(w, cw), y0 + min(h, ch)))
        sub = [row[:part.width] for row in old[:part.height]]
        new = to_index(part, sub, pal, name)
        full = [row[:] for row in old]
        for y in range(part.height):
            for x in range(part.width): full[y][x] = new[y][x]
        put_lz(rom, alloc, off, idx_to_tiles(full, raw, 8, wt), stat, pal_before)


def title(rom, alloc, stat):
    off, poff, moff = 0x352BB8, 0x3551A8, 0x355388
    raw = decode(R, off)[0]
    mp = list(struct.unpack('<600H', R[moff:moff + 1200]))
    im, sc = load_png('title_logo', 240, 160)
    # 색인 PNG지만 번호는 롬 팔레트 번호가 아니다(그림 작업 쪽 팔레트) → 색으로 롬 번호를 찾는다
    rgb = im.convert('RGB').resize((240, 160), Image.NEAREST)
    pal = [G.bgr(v & 0x7FFF) for v in struct.unpack('<240H', R[poff:poff + 480])] + [(0, 0, 0)] * 16
    nt = len(raw) // 64
    old = [[0] * 240 for _ in range(160)]
    for i, e in enumerate(mp):
        ti, hf, vf = e & 0x3FF, e >> 10 & 1, e >> 11 & 1
        for y in range(8):
            for x in range(8):
                sx = 7 - x if hf else x; sy = 7 - y if vf else y
                old[(i // 30) * 8 + y][(i % 30) * 8 + x] = raw[ti * 64 + sy * 8 + sx]
    idx = to_index(rgb, old, pal, 'title_logo')

    class _Src:
        def __getitem__(self, xy): return idx[xy[1]][xy[0]]
    src = _Src()
    tiles = [raw[i*64:(i+1)*64] for i in range(nt)]
    content = {}
    newmap = []
    newtiles = list(tiles)
    owner = {}
    for i, e in enumerate(mp):
        ti, hf, vf = e & 0x3FF, e >> 10 & 1, e >> 11 & 1
        tx, ty = (i % 30) * 8, (i // 30) * 8
        blk = bytearray(64)
        for y in range(8):
            for x in range(8):
                sx = 7 - x if hf else x; sy = 7 - y if vf else y
                blk[sy * 8 + sx] = src[tx + x, ty + y]
        blk = bytes(blk)
        if ti < nt and (owner.get(ti) in (None, blk)) and (owner.get(ti) is not None or True):
            if ti not in owner: owner[ti] = blk; newtiles[ti] = blk; newmap.append(e); continue
            if owner[ti] == blk: newmap.append(e); continue
        # 같은 타일을 다른 칸이 다르게 쓰면: 이미 있는 타일(뒤집기 포함)에서 찾고, 없을 때만 새 타일
        disp = bytes(src[tx + x, ty + y] for y in range(8) for x in range(8))
        hit = None
        for j, t in enumerate(newtiles):
            for h in (0, 1):
                for v in (0, 1):
                    if bytes(t[(7 - y if v else y) * 8 + (7 - x if h else x)] for y in range(8) for x in range(8)) == disp:
                        hit = (j, h, v); break
                if hit: break
            if hit: break
        if hit:
            j, h, v = hit
            newmap.append((e & ~0x0FFF) | j | h << 10 | v << 11); stat['타이틀 같은 타일 다시 씀'] += 1; continue
        newtiles.append(disp); k = len(newtiles) - 1
        newmap.append((e & ~0x0FFF) | k)                      # 뒤집기 없이 새 타일
        stat['타이틀 새 타일'] += 1
    assert len(newtiles) <= 1024
    data = b''.join(newtiles)
    old = decode(R, off)
    c = lz_compress(data)
    if len(data) == len(raw) and len(c) <= old[1]:
        rom[off:off+old[1]] = c + bytes(old[1] - len(c)); stat['제자리'] += 1
    else:
        refs = [o for o in range(0, 0x800000 - 3, 4) if struct.unpack_from('<I', R, o)[0] == 0x08000000 + off]
        assert refs, '타이틀 포인터 없음'
        a = alloc.put(c)
        for r in refs: struct.pack_into('<I', rom, r, 0x08000000 + a)
        stat['옮김'] += 1
    rom[moff:moff + 1200] = struct.pack('<600H', *newmap)


def link_menu(rom, stat):
    off = 0x6BB046
    im = Image.open(os.path.join(RES, 'link_menu.png'))
    assert im.size == (96, 96)
    if im.mode == 'P':
        pal = im.getpalette()[:48]
        idx = [[pal[3 * im.getpixel((x, y))] // 17 for x in range(96)] for y in range(96)]
    else:
        idx = [[im.convert('L').getpixel((x, y)) // 17 for x in range(96)] for y in range(96)]
    data = R[off:off + 144 * 32]
    rom[off:off + len(data)] = idx_to_tiles(idx, data, 4, 12)
    stat['통신 메뉴(무압축)'] += 1


def apply(rom, alloc):
    import collections
    stat = collections.Counter()
    title(rom, alloc, stat)
    pb = R[0x369DB4:0x369EB4]
    for nm, offs in [('banner_junyusho', [0x369EB4, 0x36A2DC, 0x36A7D4]), ('banner_kessho', [0x36AC58, 0x36AF5C, 0x36B280]),
                     ('banner_yusho', [0x36B4D4, 0x36B884, 0x36BD50])]:
        simple(rom, alloc, stat, nm, offs, 64, 64, 8, pb, [(0, 0), (64, 0), (128, 0)])
    for o in [0x650004, 0x650A58, 0x652F30, 0x654AA8, 0x656D98, 0x659194, 0x65A6D4, 0x65DD28, 0x65F390, 0x668D04]:
        simple(rom, alloc, stat, 'cup_%06X' % o, [o], 112, 80, 14, R[o - 0x100:o], [(0, 0)], pal_before=0x100)
    simple(rom, alloc, stat, 'main_menu', [0x676F94], 240, 160, 30, palof(0x676F94), [(0, 0)])
    for nm, offs in [('btn_taisen', [0x6768C8, 0x676C0C]), ('btn_option', [0x6794D4, 0x679818]),
                     ('btn_scenario', [0x679BDC, 0x679F3C]), ('btn_vs', [0x67A328, 0x67A67C])]:
        pals = [palof(o) or palof(offs[0]) for o in offs]
        simple(rom, alloc, stat, nm, offs, 128, 16, 16, pals, [(0, 0), (0, 18)])
    for nm, o in [('face_fudan', 0x54C724), ('face_sento', 0x54C940), ('face_make', 0x54CB58)]:
        simple(rom, alloc, stat, nm, [o], 64, 64, 8, palof(o), [(0, 0)], crop=(48, 48))
    # 리그 표 배경(8bpp 240×160): 머리 칸 「順位」 → 「순위」(11/12 실기 지적, work/graphics/league/make_league.py)
    # 팔레트는 롬 0x39A194(번호 134~204가 실기 상태 저장과 같음)
    simple(rom, alloc, stat, 'league_table', [0x35D940], 240, 160, 30, R[0x39A194:0x39A394], [(0, 0)])
    # 접수처 장면 배경(8bpp 240×104): 간판 「受付」 → 흐릿한 「접수」(11/12 사용자 확정, 원본 노란 계열 색만)
    # 팔레트는 덩어리 앞 0x100(대회 카드와 같은 묶음 구조)
    simple(rom, alloc, stat, 'scene_uketsuke', [0x5F5C6C], 240, 104, 30, R[0x5F5C6C - 0x100:0x5F5C6C], [(0, 0)], pal_before=0x100)
    link_menu(rom, stat)
    # 파츠 고르기 창 머리글 10장(무압축 8bpp, 제자리, tools/headers.py)
    import headers
    for addr, data in headers.build(R).items():
        rom[addr:addr+len(data)] = data; stat['파츠 머리글(무압축)'] += 1
    return dict(stat)
