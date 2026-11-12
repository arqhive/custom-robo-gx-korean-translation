"""파츠 고르기 창 머리글 그림 10장(0x3DC714 + 번호×0x840, 무압축 8bpp 11×3 타일, 팔레트 0x3DC6D4 → 192~223번).

- 지우기: 안쪽(3~20행, 2~85열)의 글자색 노랑(197)·그림자 검정(223)만 그 그림의 안쪽 바탕색으로(아이콘은 바탕 계열 색이라 그대로).
- 쓰기: 갈무리11 Condensed 12px 노랑 + 오른쪽·아래 1픽셀 검은 그림자(원본과 같은 방식). 짧은 이름은 원본처럼 글자 사이를 띄움.
python -X utf8 tools/headers.py  → work/graphics/headers/ 비교 시트
"""
import os, struct, sys
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(__file__))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'Custom Robo GX (Japan).gba')
FONT = os.path.join(ROOT, 'tools', 'fonts', 'Galmuri11-Condensed.ttf')
BASE, STRIDE, PAL = 0x3DC714, 0x840, 0x3DC6D4
YEL, BLK = 197, 223
# (번호, 한국어, 글자 간격: None=붙여 씀, 숫자=글자 중심 사이 픽셀)
ITEMS = [(0, '샤이닝 파이터', None), (1, '에어리얼 뷰티', None), (2, '메탈 그래플러', None),
         (3, '스트라이크 배니셔', None), (4, '라이트닝 스카이어', None), (5, '미스티 미라지', None),
         (6, '불법', 16), (7, '스페셜', 14), (8, '거너', 16), (9, '포드', 16)]
OUT = os.path.join(ROOT, 'work', 'graphics', 'headers')


def load(rom, i):
    d = rom[BASE + i * STRIDE: BASE + (i + 1) * STRIDE]
    img = [[0] * 88 for _ in range(24)]
    for t in range(33):
        tx, ty = (t % 11) * 8, (t // 11) * 8
        for y in range(8):
            for x in range(8): img[ty + y][tx + x] = d[t * 64 + y * 8 + x]
    return img


def save(img):
    out = bytearray(STRIDE)
    for t in range(33):
        tx, ty = (t % 11) * 8, (t // 11) * 8
        for y in range(8):
            for x in range(8): out[t * 64 + y * 8 + x] = img[ty + y][tx + x]
    return bytes(out)


def text_mask(text, spacing):
    font = ImageFont.truetype(FONT, 12)
    if spacing is None:
        w = int(font.getlength(text)) + 2
        im = Image.new('L', (w, 16)); ImageDraw.Draw(im).text((0, 0), text, font=font, fill=255)
    else:
        w = spacing * len(text) + 2
        im = Image.new('L', (w, 16)); dr = ImageDraw.Draw(im)
        for k, c in enumerate(text):
            cw = font.getlength(c)
            dr.text((k * spacing + (spacing - cw) / 2, 0), c, font=font, fill=255)
    px = im.load()
    pts = [(x, y) for y in range(16) for x in range(w) if px[x, y] > 127]
    x0 = min(x for x, _ in pts); x1 = max(x for x, _ in pts); y0 = min(y for _, y in pts); y1 = max(y for _, y in pts)
    return {(x - x0, y - y0) for x, y in pts}, x1 - x0 + 1, y1 - y0 + 1


def make(img, text, spacing):
    bg = img[3][2]
    new = [row[:] for row in img]
    for y in range(3, 21):
        for x in range(2, 86):
            if new[y][x] in (YEL, BLK): new[y][x] = bg
    erased = [row[:] for row in new]
    m, w, h = text_mask(text, spacing)
    ox = 2 + (84 - (w + 1)) // 2; oy = 3 + (18 - (h + 1)) // 2
    assert w + 1 <= 84, (text, w)
    for x, y in m:
        sx, sy = ox + x + 1, oy + y + 1
        if (x + 1, y + 1) not in m: new[sy][sx] = BLK
    for x, y in m: new[oy + y][ox + x] = YEL
    return erased, new


def rgb(img, pal):
    im = Image.new('RGB', (88, 24))
    for y in range(24):
        for x in range(88):
            v = img[y][x]; im.putpixel((x, y), pal[v - 192] if 192 <= v < 224 else (0, 0, 0))
    return im


def build(rom):
    """{롬 위치: 새 바이트}"""
    out = {}
    for i, text, sp in ITEMS:
        _, new = make(load(rom, i), text, sp)
        out[BASE + i * STRIDE] = save(new)
    return out


def main():
    import survey_gfx as G
    rom = open(SRC, 'rb').read()
    pal = [G.bgr(v & 0x7FFF) for v in struct.unpack('<32H', rom[PAL:PAL + 64])]
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for i, text, sp in ITEMS:
        img = load(rom, i); er, new = make(img, text, sp)
        rows.append((rgb(img, pal), rgb(er, pal), rgb(new, pal), text))
        # 지운 곳 밖 변경 0 확인
        changed = sum(1 for y in range(24) for x in range(88) if img[y][x] != new[y][x] and not (3 <= y < 21 and 2 <= x < 86))
        assert changed == 0, (i, changed)
    sc = 3
    sheet = Image.new('RGB', ((88 * 3 + 20) * sc, (24 + 4) * len(rows) * sc), (255, 255, 255))
    for k, (a, b, c, t) in enumerate(rows):
        for j, im in enumerate((a, b, c)):
            sheet.paste(im.resize((88 * sc, 24 * sc), Image.NEAREST), ((88 + 10) * j * sc, (24 + 4) * k * sc))
    sheet.save(os.path.join(OUT, 'headers_sheet.png'))
    print('시트', os.path.join(OUT, 'headers_sheet.png'))


if __name__ == '__main__':
    main()
