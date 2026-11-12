"""4단계 그림 전수 조사 도구.

python tools/survey_gfx.py lz      LZ77 999개 풀기·형식 추정·렌더(work/survey/gfx/lz, 시트 work/survey/gfx/sheets)
python tools/survey_gfx.py raw     무압축 구역을 4bpp/8bpp 타일로 렌더(work/survey/gfx/raw)
python tools/survey_gfx.py one <오프셋hex> [4|8] [폭타일] [팔레트오프셋hex]   덩어리 하나 다시 렌더
python tools/survey_gfx.py manifest  manifests/region-map.json·gfx-survey.json, 일본어 그림 시트(work/survey/gfx/jp, sheets/jp_all.png)

원본 롬은 읽기만 한다.
"""
import json, os, struct, sys
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from lz77 import decode  # noqa: E402

ROM = open(os.path.join(ROOT, 'Custom Robo GX (Japan).gba'), 'rb').read()
OUT = os.path.join(ROOT, 'work', 'survey', 'gfx')


def lz_list():
    d = json.load(open(os.path.join(ROOT, 'work', 'lz77-scan.json')))
    return sorted((o, s, c) for o, s, c, h in d)


# ---------- 팔레트 ----------
def is_pal(b):
    if len(b) < 32 or len(b) % 2:
        return False
    v = struct.unpack('<%dH' % (len(b) // 2), b)
    return sum(x >= 0x8000 for x in v) <= len(v) // 64 and len(set(v)) > max(3, len(v) // 4)


def bgr(v):
    r, g, b = v & 31, (v >> 5) & 31, (v >> 10) & 31
    return (r * 255 // 31, g * 255 // 31, b * 255 // 31)


def pal_from(b):
    v = struct.unpack('<%dH' % (len(b) // 2), b)
    return [bgr(x & 0x7FFF) for x in v]


def gray_pal(n):
    # 번호마다 구별되는 색: 0은 검정, 나머지는 밝기 순 회색+약간 색
    if n == 16:
        return [(i * 17, i * 17, i * 17) for i in range(16)]
    out = []
    for i in range(256):
        out.append(((i * 37) % 200 + 55 if i else 0, (i * 91) % 200 + 55 if i else 0, (i * 53) % 200 + 55 if i else 0))
    return out


# ---------- 렌더 ----------
def tiles_img(data, bpp, wt, pal=None, bank=0):
    tsz = 32 if bpp == 4 else 64
    nt = len(data) // tsz
    if nt == 0:
        return None
    ht = (nt + wt - 1) // wt
    im = Image.new('RGB', (wt * 8, ht * 8), (40, 0, 40))
    px = im.load()
    if pal is None:
        pal = gray_pal(16 if bpp == 4 else 256)
    for t in range(nt):
        tx, ty = (t % wt) * 8, (t // wt) * 8
        base = t * tsz
        for y in range(8):
            for x in range(8):
                if bpp == 4:
                    b = data[base + y * 4 + x // 2]
                    c = (b >> 4) if x & 1 else (b & 15)
                    c = c + bank * 16
                else:
                    c = data[base + y * 8 + x]
                px[tx + x, ty + y] = pal[c] if c < len(pal) else (255, 0, 255)
    return im


def map_img(mapd, tiles, bpp, wt, pal=None, affine=False):
    """BG 맵(u16, 또는 affine 1바이트)을 타일로 합성."""
    tsz = 32 if bpp == 4 else 64
    nt = len(tiles) // tsz
    if affine:
        ent = list(mapd)
    else:
        ent = list(struct.unpack('<%dH' % (len(mapd) // 2), mapd[:len(mapd) // 2 * 2]))
    n = len(ent)
    ht = (n + wt - 1) // wt
    im = Image.new('RGB', (wt * 8, ht * 8), (40, 0, 40))
    px = im.load()
    if pal is None:
        pal = gray_pal(16 if bpp == 4 else 256)
    for i, e in enumerate(ent):
        if affine:
            ti, hf, vf, pb = e, 0, 0, 0
        else:
            ti, hf, vf, pb = e & 0x3FF, e >> 10 & 1, e >> 11 & 1, e >> 12
        if ti >= nt:
            continue
        tx, ty = (i % wt) * 8, (i // wt) * 8
        base = ti * tsz
        for y in range(8):
            for x in range(8):
                sx = 7 - x if hf else x
                sy = 7 - y if vf else y
                if bpp == 4:
                    b = tiles[base + sy * 4 + sx // 2]
                    c = (b >> 4) if sx & 1 else (b & 15)
                    c += pb * 16
                else:
                    c = tiles[base + sy * 8 + sx]
                px[tx + x, ty + y] = pal[c] if c < len(pal) else (128, 128, 128)
    return im


# ---------- 분류 ----------
def smooth(data, bpp):
    """8×8 타일로 읽었을 때 가로 이웃 픽셀이 같은 비율."""
    tsz = 32 if bpp == 4 else 64
    nt = min(len(data) // tsz, 400)
    same = tot = 0
    for t in range(nt):
        base = t * tsz
        for y in range(8):
            if bpp == 4:
                row = []
                for x in range(4):
                    b = data[base + y * 4 + x]
                    row += [b & 15, b >> 4]
            else:
                row = data[base + y * 8: base + y * 8 + 8]
            for x in range(7):
                tot += 1
                same += row[x] == row[x + 1]
    return same / tot if tot else 0


def looks_map(data):
    if len(data) % 2 or len(data) < 64:
        return False
    hi = set(data[1::2])
    lo = set(data[0::2])
    v = struct.unpack('<%dH' % (len(data) // 2), data)
    flips = sum(1 for x in v if x & 0x0C00) / len(v)
    return len(hi) <= 24 and len(lo) > 2 * len(hi) and flips < 0.5


def classify(data, gap_pal):
    n = len(data)
    if n % 32 == 0 and n <= 512 and is_pal(data) and smooth(data, 4) < 0.35:
        return 'palette', None
    if looks_map(data):
        return 'map', None
    s4, s8 = smooth(data, 4), smooth(data, 8)
    if gap_pal is not None and len(gap_pal) >= 64 * 2 and n % 64 == 0:
        bpp = 8 if s8 >= s4 * 0.8 else 4
    else:
        bpp = 8 if s8 > s4 else 4
    return 'tiles', bpp, s4, s8


def width_for(nt):
    if nt <= 64:
        return min(8, nt)
    if nt <= 256 and nt % 16 == 0:
        return 16
    for w in (30, 32, 16):
        if nt % w == 0 and nt >= w:
            return w
    return 16 if nt >= 16 else max(nt, 1)


def pal_loose(b):
    """비트15를 무시하는 팔레트 판별(이 게임 팔레트는 비트15에 쓰레기 값이 있다)."""
    if len(b) < 32 or len(b) % 32:
        return False
    v = [x & 0x7FFF for x in struct.unpack('<%dH' % (len(b) // 2), b)]
    if len(set(v)) <= max(3, len(v) // 4):
        return False
    small = sum(1 for x in v if x < 0x400) / len(v)
    return small < 0.5


def parse_gap_all(g, ge=0):
    out = []
    for p in range(0, 4):
        if (ge + p) % 4:
            continue
        for k in (512, 448, 256, 192, 128, 96, 64, 32):
            if len(g) >= p + k and pal_loose(g[p:p + k]):
                out.append((p, g[p:p + k], p + k))
        if out:
            break
    return out


def parse_gap(g, ge=0):
    """간격 = [패딩][팔레트][맵/기타]. (팔레트 오프셋, 팔레트 바이트, 나머지 시작) 반환."""
    for p in range(0, 4):
        if (ge + p) % 4:
            continue
        for k in (512, 448, 256, 192, 128, 96, 64, 32):
            if len(g) >= p + k and pal_loose(g[p:p + k]):
                return p, g[p:p + k], p + k
    return None, None, 0


def map_from(R, nt):
    """나머지 바이트에서 맵 찾기: ('u16'|'byte', 데이터, 폭)."""
    R2 = R.rstrip(b'\xff')
    if len(R2) >= 1200:
        best = None
        for ln, w in ((2048, 32), (1280, 32), (1200, 30)):
            if len(R2) < ln:
                continue
            for st in sorted(set(range(0, len(R2) - ln + 1, 2)) & set(list(range(0, 66, 2)) + list(range(len(R2) - ln - 64, len(R2) - ln + 1, 2)))):
                m = R2[st:st + ln]
                v = struct.unpack('<%dH' % (ln // 2), m)
                if max(x & 0x3FF for x in v) >= max(nt, 1) or len(set(v)) <= 8:
                    continue
                seq = sum(1 for i in range(len(v) - 1) if v[i + 1] == v[i] + 1 and v[i])
                if best is None or seq > best[0]:
                    best = (seq, m, w, st)
        if best and best[0] > 16:
            return 'u16', best[1], best[2]
    for ln, w in ((1024, 32), (320, 20), (256, 16)):
        if len(R2) >= ln:
            m = R2[:ln]
            if max(m) < max(nt, 1) and len(set(m)) > 8:
                return 'byte', m, w
    return None


def full_pal(data, bpp, pal):
    P = [bgr(x & 0x7FFF) for x in struct.unpack('<%dH' % (len(pal) // 2), pal)]
    if bpp == 8 and len(P) < 256:
        nz = [b for b in set(data) if b]
        base = (min(nz) // 16 * 16) if nz else 0
        if base + len(P) > 256:
            base = 0
        full = [(0, 0, 0)] * 256
        for i, c in enumerate(P):
            full[base + i] = c
        return full
    return P


def color_score(data, bpp, pal):
    """팔레트를 입혔을 때 가로 이웃 픽셀 색 차이 평균(작을수록 자연스러움)."""
    P = full_pal(data, bpp, pal)
    tsz = 32 if bpp == 4 else 64
    nt = min(len(data) // tsz, 200)
    tot = n = 0
    for t in range(nt):
        base = t * tsz
        for y in range(8):
            if bpp == 4:
                row = []
                for x in range(4):
                    b = data[base + y * 4 + x]
                    row += [b & 15, b >> 4]
            else:
                row = data[base + y * 8: base + y * 8 + 8]
            for x in range(7):
                a, b = row[x], row[x + 1]
                if a and b and a != b:
                    ca = P[a] if a < len(P) else (0, 0, 0)
                    cb = P[b] if b < len(P) else (0, 0, 0)
                    tot += abs(ca[0] - cb[0]) + abs(ca[1] - cb[1]) + abs(ca[2] - cb[2])
                    n += 1
    return tot / n if n else 0


def is_lzpal(d):
    return len(d) % 32 == 0 and len(d) <= 512 and pal_loose(d) and smooth(d, 4) < 0.35


def cmd_lz():
    lz = lz_list()
    os.makedirs(os.path.join(OUT, 'lz'), exist_ok=True)
    os.makedirs(os.path.join(OUT, 'sheets'), exist_ok=True)
    recs = []
    dec = {}
    for o, s, c in lz:
        dec[o] = decode(ROM, o)[0]
    order = [o for o, _, _ in lz]
    ends = [o + c for o, _, c in lz]

    def gap_after(i):
        e = ends[i]
        n = order[i + 1] if i + 1 < len(order) else e
        return e, ROM[e:n]

    for idx, (o, s, c) in enumerate(lz):
        data = dec[o]
        rec = {'off': o, 'size': s, 'clen': c}
        if is_lzpal(data):
            rec['kind'] = 'palette'
        elif len(data) == 448:
            rec['kind'] = 'data'
        elif looks_map(data) and len(data) <= 0x2000:
            rec['kind'] = 'map'
        elif len(data) == 16384 and data.count(0) > 2000 and max(data) < 256 and smooth(data, 4) < 0.45:
            rec['kind'] = 'affmap'
        else:
            rec['kind'] = 'tiles'
        pal = None
        mp = None
        if rec['kind'] in ('tiles', 'map'):
            ge, g = gap_after(idx)
            po, pb, rest = parse_gap(g, ge)
            if pb is not None and rec['kind'] == 'tiles':
                s4_, s8_ = smooth(data, 4), smooth(data, 8)
                bpp_ = 8 if s8_ >= s4_ * 0.7 else 4
                nt_ = len(data) // (32 if bpp_ == 4 else 64)
                cands = parse_gap_all(g, ge)
                for want in ('u16', 'byte'):
                    hit = [c_ for c_ in cands if (map_from(g[c_[2]:], nt_) or ('',))[0] == want]
                    if hit:
                        po, pb, rest = hit[0]
                        break
            if pb is not None:
                pal = pb
                rec['pal'] = ['raw', ge + po, len(pb)]
                R = g[rest:]
                rge = ge + rest
            elif idx + 1 < len(order) and is_lzpal(dec[order[idx + 1]]):
                pal = dec[order[idx + 1]]
                rec['pal'] = ['lz', order[idx + 1], len(pal)]
                rge, R = gap_after(idx + 1)
            else:
                R, rge = g, ge
                if idx > 0:
                    pe, pg = gap_after(idx - 1)
                    for k in (512, 448, 256, 128, 64, 32):
                        if len(pg) >= k and pal_loose(pg[-k:]):
                            pal = pg[-k:]
                            rec['pal'] = ['raw-before', pe + len(pg) - k, k]
                            break
            if rec['kind'] == 'tiles' and pal is not None and idx > 0 and rec['pal'][0] != 'raw-before':
                # 앞 간격 팔레트와 비교해 색이 더 매끄러운 쪽을 고른다(가족마다 팔레트가 앞/뒤에 있음)
                pe, pg = gap_after(idx - 1)
                pb_before = None
                for k in (512, 448, 256, 128, 64, 32):
                    if len(pg) >= k and pal_loose(pg[-k:]):
                        pb_before = pg[-k:]
                        break
                if pb_before is not None:
                    s4_, s8_ = smooth(data, 4), smooth(data, 8)
                    bpp_ = 8 if s8_ >= s4_ * 0.7 else 4
                    if color_score(data, bpp_, pb_before) < color_score(data, bpp_, pal) * 0.8:
                        pal = pb_before
                        rec['pal'] = ['raw-before', pe + len(pg) - len(pb_before), len(pb_before)]
            if rec['kind'] == 'tiles':
                s4, s8 = smooth(data, 4), smooth(data, 8)
                if pal is not None and len(pal) > 64:
                    bpp = 8 if s8 >= s4 * 0.7 else 4
                else:
                    bpp = 8 if s8 > s4 else 4
                rec.update(bpp=bpp, s4=round(s4, 3), s8=round(s8, 3))
                nt = len(data) // (32 if bpp == 4 else 64)
                mp = None if (bpp == 8 and nt == 600) else map_from(R, nt)
                if mp:
                    rec['map'] = [mp[0], rge, len(mp[1]), mp[2]]
        P = pal_from(pal) if pal is not None else None
        if P:
            P = [bgr(x & 0x7FFF) for x in struct.unpack('<%dH' % (len(pal) // 2), pal)]
        img = None
        scr = None
        if rec['kind'] == 'tiles':
            bpp = rec['bpp']
            nt = len(data) // (32 if bpp == 4 else 64)
            wt = width_for(nt)
            rec['wt'] = wt
            usepal = P if (P and (bpp == 4 or len(P) > 16)) else None
            if usepal and bpp == 8 and len(usepal) < 256:
                # 팔레트가 256색 중 뒤쪽 칸(예: 128~159)에 올라가는 경우: 가장 작은 0 아닌 번호 기준으로 옮김
                nz = [b for b in set(data) if b]
                base = (min(nz) // 16 * 16) if nz else 0
                if base + len(usepal) > 256:
                    base = 0
                full = gray_pal(256)[:]
                for i_, col in enumerate(usepal):
                    full[base + i_] = col
                if base:
                    rec['pal_base'] = base
                usepal = full
            img = tiles_img(data, bpp, wt, usepal)
            if mp:
                scr = map_img(mp[1], data, bpp, mp[2], usepal, affine=(mp[0] == 'byte'))
        elif rec['kind'] == 'map':
            best = None
            for j in (idx - 1, idx - 2, idx + 1):
                if 0 <= j < len(order):
                    t = dec[order[j]]
                    if len(t) >= 2048 and not looks_map(t):
                        best = order[j]
                        break
            rec['tiles_from'] = best
            if best is not None:
                t = dec[best]
                bpp = 8 if smooth(t, 8) > smooth(t, 4) else 4
                ents = len(data) // 2
                wt = 30 if ents % 30 == 0 and ents % 32 else 32
                img = map_img(data, t, bpp, wt, P)
                rec['bpp'] = bpp
        elif rec['kind'] == 'affmap':
            # 128×128 affine 맵(1바이트): 이웃 8bpp 타일 덩어리와 합성
            best = None
            for j in (idx + 1, idx - 1, idx + 2, idx - 2):
                if 0 <= j < len(order):
                    t = dec[order[j]]
                    if len(t) % 64 == 0 and len(t) // 64 > max(data) and len(t) != 16384:
                        best = order[j]
                        break
            rec['tiles_from'] = best
            if best is not None:
                t = dec[best]
                ge2 = ends[order.index(best)]
                g2 = ROM[ge2:order[order.index(best) + 1]] if order.index(best) + 1 < len(order) else b''
                _, pb2, _ = parse_gap(g2, ge2)
                P2 = [bgr(x & 0x7FFF) for x in struct.unpack('<%dH' % (len(pb2) // 2), pb2)] if pb2 else None
                img = map_img(data, t, 8, 128, P2, affine=True)
                rec['bpp'] = 8
        elif rec['kind'] == 'palette':
            p = pal_from(data)
            img = Image.new('RGB', (16 * 8, ((len(p) + 15) // 16) * 8))
            dr = ImageDraw.Draw(img)
            for i, col in enumerate(p):
                dr.rectangle([(i % 16) * 8, (i // 16) * 8, (i % 16) * 8 + 7, (i // 16) * 8 + 7], fill=col)
        if img is not None:
            fn = 'lz/%06X_%s.png' % (o, rec['kind'])
            img.save(os.path.join(OUT, fn))
            rec['png'] = 'work/survey/gfx/' + fn
        if scr is not None:
            fn = 'lz/%06X_screen.png' % o
            scr.save(os.path.join(OUT, fn))
            rec['screen_png'] = 'work/survey/gfx/' + fn
        recs.append(rec)
    json.dump(recs, open(os.path.join(OUT, 'lz_index.json'), 'w'), indent=0)
    make_sheets(recs)


def make_sheets(recs, per=12, cell_w=520):
    """ROM 순서로 시트를 만든다. 큰 그림은 줄여서 한 칸에."""
    from PIL import ImageFont
    try:
        font = ImageFont.truetype('arial.ttf', 14)
    except OSError:
        font = None
    items = [r for r in recs if r.get('png') and r['kind'] not in ('palette', 'data')]
    sheets = []
    page = []
    for r in items:
        page.append(r)
        if len(page) == per:
            sheets.append(page)
            page = []
    if page:
        sheets.append(page)
    for si, page in enumerate(sheets):
        ims = []
        for r in page:
            im = Image.open(os.path.join(ROOT, r.get('screen_png') or r['png']))
            sc = 2 if im.width <= 256 else 1
            im = im.resize((im.width * sc, im.height * sc), Image.NEAREST)
            if im.width > cell_w:
                im = im.resize((cell_w, int(im.height * cell_w / im.width)), Image.NEAREST)
            ims.append((r, im))
        # 2열 배치
        cols = 2
        rows = []
        for i in range(0, len(ims), cols):
            rows.append(ims[i:i + cols])
        H = sum(max(im.height for _, im in row) + 20 for row in rows)
        W = cols * (cell_w + 10)
        sh = Image.new('RGB', (W, H), (255, 255, 255))
        dr = ImageDraw.Draw(sh)
        y = 0
        for row in rows:
            x = 0
            for r, im in row:
                lab = '%06X %s %s %dB%s%s' % (r['off'], r['kind'], ('%dbpp' % r['bpp']) if 'bpp' in r else '', r['size'],
                                             ' pal' if 'pal' in r else '', ' +map' if r.get('screen_png') else '')
                dr.text((x + 2, y + 2), lab, fill=(200, 0, 0), font=font)
                sh.paste(im, (x, y + 18))
                x += cell_w + 10
            y += max(im.height for _, im in row) + 20
        fn = os.path.join(OUT, 'sheets', 'lz_%03d_%06X.png' % (si, page[0]['off']))
        sh.save(fn)
    print('sheets', len(sheets))


def cmd_one(argv):
    o = int(argv[0], 16)
    bpp = int(argv[1]) if len(argv) > 1 else 4
    wt = int(argv[2]) if len(argv) > 2 else 16
    pal = None
    if len(argv) > 3:
        po = int(argv[3], 16)
        pal = pal_from(ROM[po:po + (512 if bpp == 8 else 32 * 16)])
    if ROM[o] == 0x10 and decode(ROM, o):
        data = decode(ROM, o)[0]
    else:
        ln = int(argv[4], 16) if len(argv) > 4 else 0x2000
        data = ROM[o:o + ln]
    im = tiles_img(data, bpp, wt, pal)
    im = im.resize((im.width * 2, im.height * 2), Image.NEAREST)
    os.makedirs(os.path.join(OUT, 'one'), exist_ok=True)
    fn = os.path.join(OUT, 'one', '%06X_%dbpp_w%d.png' % (o, bpp, wt))
    im.save(fn)
    print(fn)


def cmd_raw(argv):
    """무압축 구역 렌더: raw <시작hex> <끝hex> [4|8] [폭타일]"""
    a, b = int(argv[0], 16), int(argv[1], 16)
    bpp = int(argv[2]) if len(argv) > 2 else 4
    wt = int(argv[3]) if len(argv) > 3 else 32
    os.makedirs(os.path.join(OUT, 'raw'), exist_ok=True)
    step = 0x8000 if bpp == 4 else 0x10000
    for s in range(a, b, step):
        e = min(b, s + step)
        im = tiles_img(ROM[s:e], bpp, wt)
        if im is None:
            continue
        im = im.resize((im.width * 2, im.height * 2), Image.NEAREST)
        fn = os.path.join(OUT, 'raw', '%06X-%06X_%dbpp.png' % (s, e, bpp))
        im.save(fn)
        print(fn)



# ======================================================================
# 4단계 조사 결과(눈으로 확인한 것)와 구역 지도 만들기
# ======================================================================

# 굵은 구역(LZ 구역은 덩어리·간격 단위로 다시 쪼갠다). 경계 확신도: exact / approx(±0x200 안팎)
COARSE = [
    (0x000000, 0x0000C0, 'header', 'GBA 헤더', 'exact', '헤더 형식'),
    (0x0000C0, 0x044284, 'code', '썸 코드 + 코드 안 표·리터럴 (0x43860에 LZ 모양 189B 데이터 1개 포함, 그림 아님)', 'approx', 'push/bx 분포, 4bpp 띠 렌더(그림 없음)'),
    (0x044284, 0x0451B8, 'sound', 'm4a 음색 표(voicegroup) 4개', 'exact', '곡 헤더→voicegroup 추적'),
    (0x0451B8, 0x045880, 'sound', 'm4a 곡 표 217개(8바이트)', 'exact', '곡 표 추적'),
    (0x045880, 0x045884, 'sound', 'm4a 더미 곡 헤더', 'exact', '곡 표 추적'),
    (0x045884, 0x2F266C, 'sound', 'm4a 파형(PCM) 140개', 'exact', 'voicegroup→파형 헤더 크기 합산(연속)'),
    (0x2F266C, 0x308C44, 'sound', 'm4a 곡 트랙·곡 헤더', 'exact', '곡 헤더 트랙 포인터 범위'),
    (0x308C44, 0x31BC00, 'text', '평문 SJIS(메뉴·팁·파츠 설명 등, 디버그 문자열 포함)', 'approx', 'sjis-scan 밀도'),
    (0x31BC00, 0x321200, 'table', '포인터·스프라이트 정의 표(0x31BE74 아이콘 표, 0x31E360 전투 그림 표, 0x321060 LZ 표)', 'approx', '포인터 분포·4bpp 렌더'),
    (0x321200, 0x324F7C, 'text', '평문 SJIS', 'approx', 'sjis-scan 밀도'),
    (0x324F7C, 0x325220, 'table', 'LZ 포인터 표(0x324F7C 로봇 조각, 0x32506C PUSH START)', 'approx', '포인터 분포'),
    ('LZ', 0x325220, 0x3D4768),
    (0x3D4768, 0x3D4780, 'table', '저장 형식 문자열 EEPROM_V122', 'exact', '문자열'),
    (0x3D4780, 0x3D7768, 'table', '표(설정·데이터)', 'approx', '4bpp 렌더(그림 아님)'),
    (0x3D7768, 0x3DC768, 'raw-gfx', '무압축 4bpp 타일(파츠 메뉴 라벨 BODY/GUN/BOMB/POD/SUB/CHIP 등 영어, 버튼 테두리)', 'approx', '4bpp 렌더'),
    (0x3DC768, 0x3E57C0, 'table', '표(저엔트로피 데이터)', 'approx', '4bpp·8bpp 렌더(그림 아님)'),
    ('LZ', 0x3E57C0, 0x3E6C19),
    (0x3E6C19, 0x3E7D5C, 'table', '표(0x3E7CE4 READY/BATTLE 그림 표 등)', 'approx', '포인터'),
    (0x3E7D5C, 0x3E7D5E, 'font', '글꼴 A 글자 수(0x6B6)', 'exact', 'docs/analysis.md'),
    (0x3E7D5E, 0x3F543E, 'font', '글꼴 A 글리프 2bpp 8×16 1,719개', 'exact', 'docs/analysis.md'),
    (0x3F543E, 0x3F61AA, 'font', '글꼴 A 코드표', 'exact', 'docs/analysis.md'),
    (0x3F61AA, 0x3F659E, 'font', '1바이트→글리프 표 2개 + 글꼴 B 개수', 'approx', 'docs/analysis.md'),
    (0x3F659E, 0x3F831E, 'font', '글꼴 B 글리프 2bpp 236개', 'exact', 'docs/analysis.md'),
    (0x3F831E, 0x3F84F4, 'font', '글꼴 B 코드표', 'exact', 'docs/analysis.md'),
    (0x3F84F4, 0x3F8850, 'table', '로봇 애니 묶음 오프셋 표·묶음 머리', 'approx', '바이트 구조'),
    ('LZ', 0x3F8850, 0x4B5FA0),
    (0x4B5FA0, 0x5371D8, 'script', '시나리오 스크립트(대사 포함). 0x507FD4에 LZ 모양 39B(오탐)', 'exact', 'docs/analysis.md'),
    ('LZ', 0x5371D8, 0x692CA4),
    (0x692CA4, 0x693D3C, 'table', '포인터 표', 'approx', '포인터 분포'),
    (0x693D3C, 0x6A5BA4, 'font', '글꼴 C: 1bpp 8×8, SJIS 코드(2B)+8B, 7,332자(81 40~EA FC, JIS 제2수준 포함). 코드 0x37164·0x3AF48에서 참조', 'exact', '구조 판독·렌더'),
    (0x6A5BA4, 0x6AB000, 'table', '수치 표', 'approx', '4bpp 렌더(그림 아님)'),
    (0x6AB000, 0x6BAF26, 'text', '파츠 데이터 레코드(SJIS 이름 포함)', 'approx', 'sjis-scan 밀도 ~29%'),
    (0x6BAF26, 0x6BC246, 'raw-gfx', '무압축 4bpp: 통신 대전 메뉴 일본어 글씨 그림', 'approx', '4bpp 렌더·판독'),
    (0x6BC246, 0x6C09E6, 'unknown', '미해독: 그라데이션 타일·흑백 블록(4bpp로 보면 일부 그림, 일부 표)', 'approx', '4bpp 렌더만'),
    (0x6C09E6, 0x6C8E26, 'raw-gfx', '무압축 4bpp: DRAW 등 큰 영어 글자, 3·2·1·GO! 카운트다운', 'approx', '4bpp 렌더(폭 20)'),
    (0x6C8E26, 0x6C91E8, 'palette', '팔레트·표(0x6C9140 등)', 'approx', '참조 리터럴'),
    ('LZ', 0x6C91E8, 0x74D1F4),
    (0x74D1F4, 0x74D2B4, 'palette', '팔레트', 'approx', '포인터'),
    (0x74D2B4, 0x74FB54, 'raw-gfx', '무압축 4bpp 총 아이콘 32×16 36개(표 0x31BE74, 팔레트 0x74F6B4~)', 'exact', '표 추적·렌더'),
    (0x74FB54, 0x7501F4, 'palette', '팔레트·작은 아이콘', 'approx', '포인터'),
    (0x7501F4, 0x7611F4, 'raw-gfx', '무압축 4bpp 탄환·폭탄 스프라이트 32×32', 'approx', '4bpp 띠 렌더'),
    (0x7611F4, 0x76D1C8, 'table', '스프라이트 애니 정의 표', 'approx', '포인터 분포'),
    (0x76D1C8, 0x7AB188, 'raw-gfx', '무압축 4bpp 이펙트 스프라이트(폭발·연기 등)', 'approx', '4bpp 띠 렌더, 표 0x31DDAC'),
    (0x7AB188, 0x7AB788, 'table', '애니 정의 표', 'approx', '포인터'),
    (0x7AB788, 0x7B332C, 'raw-gfx', '무압축 4bpp 이펙트 타일', 'approx', '4bpp 렌더'),
    (0x7B332C, 0x7B632C, 'raw-gfx', '무압축 BG 애니메이션 타일(1KB씩 VRAM 0x600D200으로 복사)', 'approx', '코드 0x1ED60'),
    (0x7B632C, 0x7BB800, 'table', '표(이름 입력·메뉴 구조)', 'approx', '포인터 분포'),
    (0x7BB800, 0x7BC900, 'text', '이름 입력 글자판 SJIS', 'approx', 'sjis-scan 밀도'),
    (0x7BC900, 0x7BCE5C, 'table', '표', 'approx', '포인터'),
    (0x7BCE5C, 0x7C0400, 'raw-gfx', '무압축 4bpp 이펙트 스프라이트', 'approx', '4bpp 렌더'),
    (0x7C0400, 0x7C9400, 'table', '표(애니·크레딧 구조)', 'approx', '포인터 분포'),
    (0x7C9400, 0x7CAFB4, 'text', '스태프 크레딧·안내 SJIS', 'approx', 'sjis-scan 밀도'),
    (0x7CAFB4, 0x800000, 'empty', '빈 공간(0xFF)', 'exact', '바이트 검사'),
]

# 눈으로 확인한 일본어 그림 목록
JP = [
    dict(id='title_logo', offs=[0x352BB8], fmt='LZ77 8bpp 타일 243개 + 팔레트(무압축 0x3551A8, 224색) + 맵(무압축 u16 30×20, 0x355388)', size='240×160',
         text='カスタムロボ / ジー・エックス (영어: CUSTOM ROBO, GX, © 2002 NOISE/Nintendo)', where='타이틀 화면'),
    dict(id='banner_junyusho', offs=[0x369EB4, 0x36A2DC, 0x36A7D4], fmt='LZ77 8bpp 64×64 ×3(4096B씩), 팔레트 0x369DB4(앞 간격 128색)', size='192×64',
         text='準優勝', where='대회 결과 배너'),
    dict(id='banner_kessho', offs=[0x36AC58, 0x36AF5C, 0x36B280], fmt='LZ77 8bpp 64×64 ×3', size='192×64', text='決勝進出', where='대회 결과 배너'),
    dict(id='banner_yusho', offs=[0x36B4D4, 0x36B884, 0x36BD50], fmt='LZ77 8bpp 64×64 ×3', size='192×64', text='優勝', where='대회 결과 배너'),
]
for o, t in [(0x650004, 'エンペラーカップ'), (0x650A58, 'クイーンカップ'), (0x652F30, 'コロコロコミック'), (0x654AA8, 'スターリーカップ'),
             (0x656D98, 'チャレンジカップ'), (0x659194, 'デーモンズカップ'), (0x65A6D4, 'ナイトメアカップ'), (0x65DD28, 'ブラッディカップ'),
             (0x65F390, 'ボンバーカップ'), (0x668D04, 'ワイルドカップ')]:
    JP.append(dict(id='cup_%06X' % o, offs=[o], fmt='LZ77 8bpp 타일 140개(14×10 순서대로), 팔레트 = 덩어리-0x100 (128색, 코드 0x800E930 표 0x3E5134)',
                   size='112×80', text=t, where='대회 타이틀 카드'))
JP += [
    dict(id='main_menu', offs=[0x676F94], fmt='LZ77 8bpp 타일 600개(30×20 전체 화면, 맵 없음)', size='240×160', text='メインメニュー', where='메인 메뉴 배경'),
    dict(id='btn_taisen', offs=[0x6768C8, 0x676C0C], fmt='LZ77 8bpp 타일 32개(16×2), 보통/선택 2벌', size='128×16', text='対戦記録', where='메인 메뉴 버튼'),
    dict(id='btn_option', offs=[0x6794D4, 0x679818], fmt='LZ77 8bpp 16×2, 2벌', size='128×16', text='オプション', where='메인 메뉴 버튼'),
    dict(id='btn_scenario', offs=[0x679BDC, 0x679F3C], fmt='LZ77 8bpp 16×2, 2벌', size='128×16', text='シナリオ モード', where='메인 메뉴 버튼'),
    dict(id='btn_vs', offs=[0x67A328, 0x67A67C], fmt='LZ77 8bpp 16×2, 2벌', size='128×16', text='VS. バトル', where='메인 메뉴 버튼'),
    dict(id='face_fudan', offs=[0x54C724], fmt='LZ77 8bpp 64 타일(얼굴 칸 48×48 사용)', size='48×48', text='ふだん', where='얼굴 그림 칸(표정 이름 자리 추정)'),
    dict(id='face_sento', offs=[0x54C940], fmt='LZ77 8bpp 64 타일(48×48)', size='48×48', text='せんとう', where='얼굴 그림 칸'),
    dict(id='face_make', offs=[0x54CB58], fmt='LZ77 8bpp 64 타일(48×48)', size='48×48', text='負け', where='얼굴 그림 칸'),
    dict(id='scene_uketsuke', offs=[0x5F5C6C], fmt='LZ77 8bpp 타일 390개(30×13 순서대로), 팔레트 앞 간격 128색(번호 128~)', size='240×104',
         text='受付 (영어 INFORMATION 함께, 배경 속 작은 간판)', where='이벤트 배경(접수처)'),
    dict(id='link_menu', offs=[0x6BAF26], fmt='무압축 4bpp 0x6BAF26~0x6BC246(약 4.8KB), 배치·팔레트 미확정(폭 12타일로 대부분 읽힘)', size='약 96×200',
         text='通信エラーが発生しました / バトルにもどる / リタイアする / 本当にリタイアしますか? / はい / いいえ', where='통신 대전 일시정지·오류 메뉴'),
]
SUSPECT = [
    dict(offs=[0x5AE654], note='이벤트 배경(쇼핑몰) 왼쪽 위 빨간 세로 깃발: 글자 모양이 있으나 8px 안팎이라 판독 불가. 일본어일 수 있음'),
    dict(offs=[0x6BC246], note='0x6BC246~0x6C09E6 무압축 미해독 구역(일부 그림처럼 보임)'),
]
EN = [
    ('0x33C408~0x33E0CC (LZ 4bpp 2048B ×8)', 'PERFECT / YOU WIN!'),
    ('0x38C354~0x38E038 (LZ 4bpp 256B ×49)', 'PUSH START 애니메이션'),
    ('0x3E57C0 (LZ 8bpp 16×6)', 'READY!'),
    ('0x3E5F24 (LZ 8bpp 25×8)', 'BATTLE!'),
    ('0x36E548', 'Nintendo 로고'), ('0x36EF5C', 'NOISE 로고'),
    ('0x35B620~0x35B91C', '1st / 2 / 3 / 4 순위'),
    ('0x66F99C~0x672070', '숫자 0~9'), ('0x6CB8BC, 0x6CBDBC', '숫자 1~6 게이지'),
    ('0x56F53C, 0x56F990, 0x56FDE4', 'AUTO 아이콘'),
    ('0x3A3AD8(맵)+0x3A308C', 'GX 카드 무늬'),
    ('0x651464, 0x65786C, 0x65B548, 0x65C780, 0x65FDA8, 0x664984', '대회 카드: SUPERDOME, CHAMPIONS CUP, NOISE, FRESH ROBO, CUSTOM ROBO CUP, MARINE PO..'),
    ('0x5AA8C8, 0x5BE758, 0x5CBD04, 0x5D1500, 0x5C9478, 0x5D5D48, 0x612AB8', '이벤트 배경 간판: ROBOCUP, INFOMATION, WELCOME BATTLE, PASSWORD, 모니터 글씨'),
    ('0x3D7768~0x3DC768 (무압축)', '파츠 메뉴 라벨 BODY/GUN/BOMB/POD/SUB/CHIP'),
    ('0x6C09E6~0x6C6DE6 (무압축)', 'DRAW 등 큰 영어 글자'),
    ('0x6C6DE6~0x6C8E26 (무압축)', '3 / 2 / 1 / GO!'),
]


def render_jp():
    """일본어 그림을 실제 모양대로 다시 그려 시트로 만든다."""
    os.makedirs(os.path.join(OUT, 'jp'), exist_ok=True)
    R = ROM
    pngs = {}

    def save(name, im, sc=2):
        im = im.resize((im.width * sc, im.height * sc), Image.NEAREST)
        fn = os.path.join(OUT, 'jp', name + '.png')
        im.save(fn)
        pngs[name] = 'work/survey/gfx/jp/' + name + '.png'
        return im

    # 타이틀
    d = decode(R, 0x352BB8)[0]
    P = full_pal(d, 8, R[0x3551A8:0x3551A8 + 448])
    save('title_logo', map_img(R[0x355388:0x355388 + 1200], d, 8, 30, P))
    # 배너 3종(64×64 ×3)
    pb = R[0x369DB4:0x369EB4]
    for nm, offs in [('banner_junyusho', [0x369EB4, 0x36A2DC, 0x36A7D4]), ('banner_kessho', [0x36AC58, 0x36AF5C, 0x36B280]),
                     ('banner_yusho', [0x36B4D4, 0x36B884, 0x36BD50])]:
        im = Image.new('RGB', (64 * 3, 64))
        for i, o in enumerate(offs):
            dd = decode(R, o)[0]
            im.paste(tiles_img(dd, 8, 8, full_pal(dd, 8, pb)), (i * 64, 0))
        save(nm, im)
    # 대회 카드
    for o in [0x650004, 0x650A58, 0x652F30, 0x654AA8, 0x656D98, 0x659194, 0x65A6D4, 0x65DD28, 0x65F390, 0x668D04]:
        dd = decode(R, o)[0]
        save('cup_%06X' % o, tiles_img(dd, 8, 14, full_pal(dd, 8, R[o - 0x100:o])))
    # 메인 메뉴
    idx = json.load(open(os.path.join(OUT, 'lz_index.json')))
    byoff = {x['off']: x for x in idx}

    def palof(o):
        x = byoff[o]
        if 'pal' not in x:
            return None
        k, a, n = x['pal']
        return decode(R, a)[0] if k == 'lz' else R[a:a + n]
    dd = decode(R, 0x676F94)[0]
    pp = palof(0x676F94)
    save('main_menu', tiles_img(dd, 8, 30, full_pal(dd, 8, pp) if pp else None))
    for nm, offs in [('btn_taisen', [0x6768C8, 0x676C0C]), ('btn_option', [0x6794D4, 0x679818]),
                     ('btn_scenario', [0x679BDC, 0x679F3C]), ('btn_vs', [0x67A328, 0x67A67C])]:
        im = Image.new('RGB', (128, 34), (255, 255, 255))
        for i, o in enumerate(offs):
            dd = decode(R, o)[0]
            pp = palof(o) or palof(offs[0])
            im.paste(tiles_img(dd, 8, 16, full_pal(dd, 8, pp) if pp else None), (0, i * 18))
        save(nm, im)
    for nm, o in [('face_fudan', 0x54C724), ('face_sento', 0x54C940), ('face_make', 0x54CB58)]:
        dd = decode(R, o)[0]
        pp = palof(o)
        save(nm, tiles_img(dd, 8, 8, full_pal(dd, 8, pp) if pp else None).crop((0, 0, 48, 48)), 3)
    dd = decode(R, 0x5F5C6C)[0]
    save('scene_uketsuke', tiles_img(dd, 8, 30, full_pal(dd, 8, R[0x5F5C6C - 0x100:0x5F5C6C])))
    save('link_menu', tiles_img(R[0x6BAF26:0x6BC246], 4, 12), 3)
    # 모음 시트
    ims = [(k, Image.open(os.path.join(ROOT, v))) for k, v in pngs.items()]
    W = 1000
    x = y = rowh = 0
    pos = []
    for k, im in ims:
        if x + im.width > W:
            x = 0
            y += rowh + 20
            rowh = 0
        pos.append((k, im, x, y))
        x += im.width + 10
        rowh = max(rowh, im.height)
    sh = Image.new('RGB', (W, y + rowh + 20), (255, 255, 255))
    dr = ImageDraw.Draw(sh)
    for k, im, x, y in pos:
        dr.text((x, y), k, fill=(200, 0, 0))
        sh.paste(im, (x, y + 14))
    sh.save(os.path.join(OUT, 'sheets', 'jp_all.png'))
    return pngs


def build_regions():
    lz = lz_list()
    regions = []
    for c in COARSE:
        if c[0] == 'LZ':
            a, b = c[1], c[2]
            chunks = [(o, s_, cl) for o, s_, cl in lz if a <= o < b]
            pos = a
            for o, s_, cl in chunks:
                if o > pos:
                    regions.append(gap_region(pos, o))
                regions.append(dict(start=o, end=o + cl, type='lz', desc='LZ77 덩어리(풀면 %d바이트)' % s_, confidence='exact', method='BIOS LZ77 0x10 풀기'))
                pos = o + cl
            if pos < b:
                regions.append(gap_region(pos, b))
        else:
            a, b, t, desc, conf, meth = c
            regions.append(dict(start=a, end=b, type=t, desc=desc, confidence=conf, method=meth))
    # 검사: 빈틈·겹침 없이 8MB
    regions.sort(key=lambda r: r['start'])
    p = 0
    for r in regions:
        assert r['start'] == p, (hex(p), hex(r['start']))
        assert r['end'] > r['start']
        p = r['end']
    assert p == len(ROM) == 0x800000
    for r in regions:
        r['size'] = r['end'] - r['start']
        r['start'] = '0x%06X' % r['start']
        r['end'] = '0x%06X' % r['end']
    return regions


def gap_region(a, b):
    g = ROM[a:b]
    n = b - a
    if n <= 3:
        return dict(start=a, end=b, type='padding', desc='정렬 채움', confidence='exact', method='크기')
    po, pb, rest = parse_gap(g, a)
    if pb is not None:
        tail = n - rest
        d = '팔레트 %d색' % (len(pb) // 2)
        if tail > 3:
            mp = map_from(g[rest:], 1024)
            d += ' + ' + ('맵(%s)' % mp[0] if mp else '머리/표 %d바이트' % tail)
        return dict(start=a, end=b, type='lz-gap', desc=d, confidence='approx', method='팔레트 판별(pal_loose)')
    if g.count(0xFF) == n:
        return dict(start=a, end=b, type='empty', desc='빈 공간', confidence='exact', method='바이트 검사')
    mp = map_from(g, 1024)
    if mp:
        return dict(start=a, end=b, type='lz-gap', desc='맵(%s)' % mp[0], confidence='approx', method='맵 판별')
    return dict(start=a, end=b, type='lz-gap', desc='머리/표 %d바이트' % n, confidence='approx', method='크기')


def cmd_manifest():
    regions = build_regions()
    os.makedirs(os.path.join(ROOT, 'manifests'), exist_ok=True)
    json.dump(dict(rom='Custom Robo GX (Japan).gba', size=len(ROM), total=sum(r['size'] for r in regions), regions=regions),
              open(os.path.join(ROOT, 'manifests', 'region-map.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    pngs = render_jp()
    idx = json.load(open(os.path.join(OUT, 'lz_index.json')))
    jp_offs = {o for j in JP for o in j['offs']}
    sus = {o for j in SUSPECT for o in j['offs']}
    items = []
    for x in idx:
        o = x['off']
        e = dict(off='0x%06X' % o, source='lz', size=x['size'], clen=x['clen'], kind=x['kind'], bpp=x.get('bpp'),
                 pal=x.get('pal'), map=x.get('map'), png=x.get('screen_png') or x.get('png'),
                 japanese='yes' if o in jp_offs else ('suspect' if o in sus else 'no'))
        if e['pal'] and e['pal'][0] in ('raw', 'raw-before'):
            e['pal'] = [e['pal'][0], '0x%06X' % e['pal'][1], e['pal'][2]]
        elif e['pal']:
            e['pal'] = ['lz', '0x%06X' % e['pal'][1], e['pal'][2]]
        if e['map']:
            e['map'] = [e['map'][0], '0x%06X' % e['map'][1], e['map'][2], e['map'][3]]
        if x['kind'] in ('palette', 'data'):
            e['japanese'] = 'n/a'
        items.append(e)
    for r in regions:
        if r['type'] == 'raw-gfx':
            items.append(dict(off=r['start'], end=r['end'], source='raw', size=r['size'], kind='raw-gfx', desc=r['desc'],
                              japanese='yes' if r['start'] == '0x6BAF26' else 'no'))
    jp = []
    for j in JP:
        jj = dict(j)
        jj['offs'] = ['0x%06X' % o for o in j['offs']]
        jj['sheet'] = pngs.get(j['id'])
        jp.append(jj)
    out = dict(
        note='LZ77 999개 전부 + 무압축 그림 구역. japanese: yes=일본어 글자 확인, suspect=판독 불가 의심, no=없음/영어, n/a=팔레트·데이터',
        japanese_images=jp, suspect=[dict(offs=['0x%06X' % o for o in s_['offs']], note=s_['note']) for s_ in SUSPECT],
        english_only=[dict(where=a, text=b) for a, b in EN],
        fonts=[dict(name='글꼴 A', range='0x3E7D5E-0x3F543E', note='본문 2bpp 8×16, 텍스트 작업 대상'),
               dict(name='글꼴 B', range='0x3F659E-0x3F831E', note='작은 표 2bpp'),
               dict(name='글꼴 C(새로 찾음)', range='0x693D3C-0x6A5BA4', note='1bpp 8×8 SJIS 7,332자, 용도 미확인(코드 0x37164·0x3AF48 참조)')],
        items=items)
    json.dump(out, open(os.path.join(ROOT, 'manifests', 'gfx-survey.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    from collections import Counter
    c = Counter(r['type'] for r in regions)
    sz = Counter()
    for r in regions:
        sz[r['type']] += r['size']
    for k in sorted(c):
        print(k, c[k], sz[k])
    print('regions', len(regions), 'total', sum(r['size'] for r in regions))

if __name__ == '__main__':
    c = sys.argv[1] if len(sys.argv) > 1 else 'lz'
    if c == 'lz':
        cmd_lz()
    elif c == 'one':
        cmd_one(sys.argv[2:])
    elif c == 'raw':
        cmd_raw(sys.argv[2:])
    elif c == 'manifest':
        cmd_manifest()
