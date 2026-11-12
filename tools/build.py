"""8단계 빌드: 번역·글꼴·이름 입력·비밀번호·그림 글씨를 원본 롬에 넣는다.

python -X utf8 tools/build.py [--no-gfx] [--no-dialogue] [--no-sjis] [--no-name]
  → build/Custom Robo GX (Japan) [KO vX].gba

- 롬 크기는 원본 8MB 그대로(확장하지 않음, 사용자 기준 「개조는 최소한」). 새 데이터는 FREE_REGIONS(원본 끝 빈 공간,
  옛 글꼴 A·B 자리)와, 옮긴 대사의 원래 자리에 남는 빈칸(건너뛰기 뒤라 읽히지 않음)에 나눠 둔다.
- 글꼴 A를 새로 짠다: 원래 기호·가나(첫 바이트 0x81~0x87) 칸 + 번역에 필요한 기호 + 한글 고정 코드(name_input.ORDER).
  코드 정렬 순 = 글리프 번호. 문맥 리터럴(0x8004C80·0x801D8A4)의 글리프·코드표·개수 포인터를 바꾼다.
  1바이트 표 두 개(평문 ASCII 0x3F61AA, 대사 0x3F63AA)는 코드 기준으로 다시 계산해 제자리에 쓴다.
- 대사: 단어 단위 줄바꿈({05}). 원래 자리에 들어가면 제자리(+`01 FD 원래끝`), 아니면 `01 FE 새주소` 건너뛰기.
  6바이트 미만 짧은 대사는 제자리에서 {04}로 길이를 맞춘다.
- 평문 SJIS: 들어가면 제자리, 안 들어가거나 다른 문자열과 겹치면 새 자리로 옮기고 포인터를 바꾼다.
"""
import collections, json, os, re, struct, sys
from PIL import Image, ImageDraw, ImageFont
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
sys.path.insert(0, os.path.dirname(__file__))
import gxtext as g
import name_input as N
import script as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'Custom Robo GX (Japan).gba')
VERSION = 'v1.0f'
OUT = os.path.join(ROOT, 'build', 'Custom Robo GX (Japan) [KO %s].gba' % VERSION)
FONT = os.path.join(ROOT, 'tools', 'fonts', 'Galmuri11-Condensed.ttf')
TR = os.path.join(ROOT, 'work', 'translation')

ROM_SIZE = 0x800000
# 새 데이터를 둘 수 있는 원본 안 구역: 끝 0xFF 빈 공간, 옛 글꼴 A(개수+글리프+코드표, 새 글꼴로 바꿔 안 씀),
# 옛 글꼴 B(글리프+코드표+1바이트 표, 문맥 B를 글꼴 A로 돌려 안 씀). 이 구역을 가리키는 진짜 포인터는 문맥 리터럴뿐(확인함).
FREE_REGIONS = [(0x7CAFB4, 0x800000), (0x3E7D5C, 0x3F5DAA), (0x3F659C, 0x3F86F4)]
GLYPHS, CODES, COUNT = 0x3E7D5E, 0x3F543E, 0x3E7D5C
MAP1, BYTEMAP = 0x3F61AA, 0x3F63AA          # 평문 1바이트(256×u16, 값=글리프 번호), 대사 1바이트(값+1=글리프 번호)
CTX_LITS = [(0x4C80, 0x083E7D5E), (0x4C84, 0x083F543E), (0x4C90, 0x083E7D5C),
            (0x1D8A4, 0x083E7D5E), (0x1D8A8, 0x083F543E), (0x1D8B8, 0x083E7D5C)]
NAMELEN = 7                                    # {0A}(주인공 이름) 폭 가정
SPACE = 0x02                                   # 대사 1바이트 02 = 전각 공백(표 값 0)
# 번역문의 U+00A0 은 공백 한 칸으로 넣되 줄 첫머리에서도 지우지 않는다(가운데 맞춤용)
SPACES = ' 　 '
# 01 FE 건너뛰기를 따라가지 못하는 화면의 글 → 옮기지 않고 제자리에 맞춘다(글자는 1바이트 칸 우선)
NO_JUMP = {0x50CCF3, 0x50CDF5}                 # 상태창 「プレイ時間」(11/12 실기: 옮기자 「9」「1」만 보임)
SKIP_RANGES = [(0x7B637C, 0x7B7400), (0x7C40D0, 0x7C5000)]   # 이름 입력 격자·탁점 표(격자는 name_input이 씀), 안 쓰는 사본
SUBST = {'·': '・', '~': '～', '壱': '†', '弐': '‡'}   # 壱·弐 → 아이콘 칸(ICON)
# 자동 조사: 대사 1바이트 F3~F7 → 표 값 0xFFEF+k → 글자 그리기 훅(0x800CD2C)이 바로 앞 글자 받침을 보고 골라 그림
PARTICLES = [('을(를)',), ('이(가)',), ('은(는)',), ('(으)로',), ('과(와)', '와(과)')]
PART_OUT = [('를', '을', '을'), ('가', '이', '이'), ('는', '은', '은'), ('로', '으로', '로'), ('와', '과', '과')]   # 받침 없음 / 받침 / ㄹ받침
PBYTE = 0xF3
LAST = 0x0203FFF0                              # 마지막으로 그린 글자 번호(EWRAM 끝, 코드 참조 최대 0x0203C568)


class Alloc:
    """빈 구역 여러 개에서 가장 잘 맞는(남는 칸이 가장 적은) 자리를 고른다."""
    def __init__(self, rom, regions):
        self.rom, self.free = rom, [list(r) for r in regions]
        self.used = 0

    def add(self, a, b):
        if b - a >= 4: self.free.append([a, b])

    def reserve(self, n, align=4):
        best = None
        for r in self.free:
            a = (r[0] + align - 1) & ~(align - 1)
            if a + n <= r[1] and (best is None or r[1] - a - n < best[0]): best = (r[1] - a - n, r, a)
        assert best, '빈 공간 부족(%d바이트)' % n
        _, r, a = best
        if a > r[0]: self.free.append([r[0], a])
        r[0] = a + n
        self.used += n
        self.rom[a:a+n] = b'\xff' * n
        return a

    def put(self, data, align=4):
        a = self.reserve(len(data), align)
        self.rom[a:a+len(data)] = data
        return a

    def left(self):
        return sum(b - a for a, b in self.free)


def u32(b, o): return struct.unpack_from('<I', b, o)[0]


# ---------------------------------------------------------------- 번역 읽기
def load():
    B, O = os.path.join(TR, 'batches'), os.path.join(TR, 'out')
    ex = set(json.load(open(os.path.join(TR, 'exclude.json'), encoding='utf-8')))
    jp2ko, raw = {}, []
    for f in sorted(os.listdir(B)):
        items = json.load(open(os.path.join(B, f), encoding='utf-8'))
        tr = json.load(open(os.path.join(O, f), encoding='utf-8'))['translations']
        for x in items:
            if x['id'] in ex or x['id'] not in tr: continue
            if f.startswith('dlg'): jp2ko[x['jp']] = tr[x['id']]
            else: raw.append((x, tr[x['id']]))
    dlg = [e for e in json.load(open(os.path.join(TR, 'dialogue.json'), encoding='utf-8')) if e['id'] not in ex]
    # 대사는 ID별 번역(out-id, 11/14 재번역)을 먼저 쓰고, 아직 없는 ID만 옛 원문 묶음 번역으로
    id2ko = {}
    OI = os.path.join(TR, 'out-id')
    if os.path.isdir(OI):
        for f in sorted(os.listdir(OI)):
            id2ko.update(json.load(open(os.path.join(OI, f), encoding='utf-8'))['translations'])
    for e in dlg:
        e['ko'] = id2ko[e['id']] if e['id'] in id2ko else jp2ko[e['jp']]
    return jp2ko, raw, dlg


# ---------------------------------------------------------------- 문자 → 코드
def dlg_char(c):
    """대사 글자 → 평문 코드로 바꿀 글자(반각 ASCII는 전각으로)."""
    c = SUBST.get(c, c)
    if c == "'": return '’'                  # 전각 ＇(0xFA57)는 한글 코드 뒤라 대사 번호 한계를 넘음
    if c == '"': return '”'
    if '!' <= c <= '~': c = chr(ord(c) + 0xFEE0)
    return c


def code_of(c):
    """글자 → 2바이트 코드(int)."""
    if c in N.IDX: b = N.idx2code(N.IDX[c])
    else: b = SUBST.get(c, c).encode('cp932')
    assert len(b) == 2, c
    return b[0] << 8 | b[1]


def sjis_bytes(t):
    out = bytearray()
    for c in t:
        if c in N.IDX: out += N.idx2code(N.IDX[c])
        elif ord(c) < 0x80: out.append(ord(c))
        else:
            b = SUBST.get(c, c).encode('cp932')
            if len(b) == 1 and ord(c) >= 0x80: raise ValueError('반각 가나 %r' % c)
            out += b
    return bytes(out)


HELP_RANGE = (0x311014, 0x314400)    # 도움말(용어 설명·게임 설명): 기본 대사창 29칸·5줄, 0x800D55C 평문 출력
# 11/13: 시작을 0x311600 → 0x311014(「로보 배틀에 무적의 커스터마이즈는…」)로 당김. 그 앞 도움말 8개가 낱말 줄바꿈을 못 받아
#        실기에서 낱말이 잘리고 줄 첫머리에 빈칸이 생김(사용자 스크린샷 5장). 바로 앞 311004 「로보/파츠」부터는 메뉴 글.
HELP_W, HELP_LINES = 28, 5
HANG = '.,!?…」』)）'


def help_wrap(t):
    """도움말 평문을 단어 단위로 꺾는다($N), 줄 첫 공백 제거, 「·」 항목 다음 줄은 한 칸 들여쓰기, 5줄 넘는 쪽은 $P로 나눔."""
    paras = re.split(r'(\$[NnPpCc])', t)
    out, lines = [], 1
    in_item = False
    for k, part in enumerate(paras):
        if re.fullmatch(r'\$[NnPpCc]', part or ''):
            if part in ('$P', '$p', '$C', '$c'):
                lines = 1; out.append(part); continue
            lines += 1
            out.append('$P' if lines > HELP_LINES else part)        # 원문 줄바꿈이 쪽을 넘기면 쪽 넘김으로
            if lines > HELP_LINES: lines = 1
            continue
        if not part: continue
        first = re.sub(r'\$[A-Za-z]', '', part)[:1]
        # 「·」 항목을 손으로 꺾은 다음 줄($N 뒤, 「·」 없이 시작)도 항목의 이어지는 줄 → 한 칸 들여쓰기
        cont = k >= 2 and paras[k - 1] in ('$N', '$n') and first not in '·・' and in_item
        bullet = first in '·・' or cont
        in_item = bullet
        words = re.split(r'( +|　)', part)
        col = 0; line = ' ' if cont else ''; col = len(line)
        toks = [w for w in words if w != '']
        for w in toks:
            vis = len(re.sub(r'\$[A-Za-z]', '', w))
            if w.strip() == '':
                if col == 0: continue
                line += w; col += vis; continue
            need = col + vis
            hang = w.rstrip()[-1:] in HANG if re.sub(r'\$[A-Za-z]', '', w) else False
            if col > 0 and need > HELP_W and not (hang and need == HELP_W + 1):
                line = line.rstrip(' 　')
                out.append(line); out.append('$N'); lines += 1
                if lines > HELP_LINES:
                    out[-1] = '$P'; lines = 1
                line = ' ' if bullet else ''; col = len(line)
            line += w; col += vis
        out.append(line)
    return ''.join(out)


def raw_text(x, ko):
    """평문 번역을 롬에 넣을 글로(도움말·로보 설명은 줄바꿈 처리)."""
    if is_summary(x):
        return summary_wrap(punct_space(ko))
    if HELP_RANGE[0] <= int(x['id'], 16) < HELP_RANGE[1] and re.search(r'\$[NnRrBb]', x['jp']):
        ko = help_wrap(ko)
    w = window_of(x)
    if w and w['mode'] == 'desc' and x['jp'][:1] == '・':
        return desc_wrap(punct_space(ko), w['body'])
    return punct_space(ko)


# 설명·정보창 표 — 창마다 폭·줄 수를 여기 한 곳에만 적는다. 줄바꿈(raw_text)과 넘침 검사(check_windows)가 둘 다 이 표를 읽는다.
# (11/12 반성: 창별로 받은 폭·줄 수를 주석에만 적고 한 숫자로 돌려써서 포드·거너 넘침, 봄 들여쓰기 회귀가 남)
#  mode 'desc': 「·」 항목마다 빌드가 낱말 단위로 꺾음. body = 앞 「·」/들여쓰기 한 칸을 뺀 본문 폭, lines = 최대 줄 수
#  mode 'char': 게임이 글자 단위로 꺾음(빌드는 꺾지 않음). cells = 한 줄 전체 칸, lines = 보이는 줄 수(넘치면 앞줄이 안 보임)
WINDOWS = [
    dict(name='로보 설명', ranges=[(0x309C00, 0x30A8A0)], mode='desc', body=14, lines=7, src='11/11 사용자 실측: · 빼고 14자. 11/12 실기 확인: 데빌 렉스 「·메탈 그래플러형을 바탕으로」(· 뒤 14자) 한 줄'),
    dict(name='건 설명', ranges=[(0x30A8A0, 0x30C000)], mode='desc', body=14, lines=7, src='11/12 실기 확인: 바이킹 액스 「·α샷은 사정거리가 길어지고」(· 뒤 14자) 한 줄'),
    dict(name='봄 설명', ranges=[(0x30C000, 0x30CD60)], mode='desc', body=14, lines=7, src='11/12 실기 확인: 제미니 봄 「·움직임이 빠른 상대에 맞춰」(· 뒤 14자) 한 줄'),
    dict(name='포드 설명', ranges=[(0x30CD60, 0x30DA00)], mode='desc', body=13, lines=6, src='11/12 실기: · 포함 14칸(거너와 같은 창)'),
    dict(name='거너 설명', ranges=[(0x30DA00, 0x30E300)], mode='desc', body=13, lines=6, src='11/12 시험 롬(불법 시커 거너에 · 뒤 14자 두 줄): 14번째 글자가 다음 줄로 → · 뒤 13자 확정'),
    dict(name='칩 설명', ranges=[(0x30E300, 0x30E900)], mode='desc', body=25, lines=7, src='11/12 사용자'),
    dict(name='아이템 설명', ranges=[(0x310C44, 0x310EF0)], mode='char', cells=8, lines=3, src='11/12 실기: 로보 라이선스 첫 줄이 밀려 안 보임'),
    dict(name='홀로세움 정보', ranges=[(0x318100, 0x318340)], mode='char', cells=16, lines=2, src='11/12 실기: 팝 앤 토이즈A 「켜」'),
]
# 파츠 정보 화면은 끝의 빈 줄($n)까지 센 전체 줄이 이보다 많으면 「パーツ説明テキストが画面からはみ出た」로 멈춘다
# (11/12 실기: 트윈 거너 30DD64가 6줄+빈 줄 3 = 9줄에서 멈춤. 원문은 최대 8줄)
PARTS_TOTAL = 8
# 옛 이름(다른 스크립트용)
DESC_14 = [r for w in WINDOWS if w['mode'] == 'desc' and w['body'] >= 13 and w['body'] <= 14 for r in w['ranges']]
DESC_W = 14


def window_of(x):
    o = int(x['id'], 16)
    for w in WINDOWS:
        if any(a <= o < z for a, z in w['ranges']): return w
    return None


def check_windows(raw):
    """창 표 기준 넘침: [(창, id, 까닭, 화면 줄)]. 빌드가 이게 있으면 롬을 쓰지 않고 멈춘다."""
    vis = lambda s: len(re.sub(r'#[A-Z0-9]', '#', re.sub(r'\$[A-Za-z]', '', s)))   # #P 같은 아이콘은 한 칸(11/12 실기 「월 봄P」)
    bad = []
    for x, ko in raw:
        w = window_of(x)
        if not w: continue
        s = raw_text(x, ko)
        if w['mode'] == 'desc':
            if x['jp'][:1] != '・': continue          # 꼬리 조각·이름 등은 이 창 글이 아님
            lines = re.split(r'\$[nN]', s)
            if len(lines) > PARTS_TOTAL:
                bad.append((w['name'], x['id'], '끝 빈 줄까지 %d줄 > %d줄(게임 오류)' % (len(lines), PARTS_TOTAL), ' / '.join(lines)))
            while lines and lines[-1] == '': lines.pop()
            wide = [l for l in lines if vis(l) > w['body'] + 1]
            if wide: bad.append((w['name'], x['id'], '%d칸 넘는 줄' % (w['body'] + 1), wide[0]))
            if len(lines) > w['lines']: bad.append((w['name'], x['id'], '%d줄 > %d줄' % (len(lines), w['lines']), ' / '.join(lines)))
        else:
            t = re.sub(r'\$[a-z]|#[A-Z0-9]', '', s)
            n = sum(max(1, -(-len(p) // w['cells'])) for p in t.split('$N'))
            if n > w['lines']: bad.append((w['name'], x['id'], '%d줄 > %d줄(%d칸씩)' % (n, w['lines'], w['cells']), t))
    return bad


def text_drift(raw):
    """회귀 검사: 직전 빌드의 (번역, 화면 글)과 비교해 번역은 같은데 화면 글이 달라진 평문을 돌려준다.
    도구(줄바꿈 함수 등)를 고쳐서 생긴 변화가 여기 뜬다(11/12 「 월 봄」 들여쓰기가 v0.1.30부터 사라진 것 같은 회귀)."""
    p = os.path.join(ROOT, 'build', 'raw_texts.json')
    old = json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}
    now = {x['id']: [ko, raw_text(x, ko)] for x, ko in raw}
    drift = [(i, repr(old[i][1]), '→', repr(v[1])) for i, v in now.items() if i in old and old[i][0] == v[0] and old[i][1] != v[1]]
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(now, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
    return drift

# 파츠 그림 밑 두 줄 요약(11/12 실기): 한 줄 9칸·2줄. 원문은 「9자$N9자」 꼴.
# 번역의 $N 자리는 무시하고 낱말 단위로 9칸씩 다시 꺾는다(들여쓰기 없음).
SUMMARY_RANGE, SUMMARY_W = (0x314000, 0x315100), 9


def is_summary(x):
    parts = x['jp'].split('$N')
    return (SUMMARY_RANGE[0] <= int(x['id'], 16) < SUMMARY_RANGE[1]
            and len(parts) == 2 and all(len(p) <= 10 for p in parts))


def summary_wrap(t):
    t = re.sub(' +', ' ', t.replace('$N', ' ').replace('　', ' ')).strip()
    return desc_wrap(t, SUMMARY_W).replace('$n　', '$N')


def desc_wrap(t, W):
    """「·」 항목마다 낱말 단위로 $n을 넣는다. 쉼표·마침표 뒤(빈칸이 빠진 자리)에서도 꺾을 수 있다."""
    vis = lambda s: len(re.sub(r'#[A-Z0-9]', '#', re.sub(r'\$[A-Za-z]', '', s)))   # #P 같은 아이콘은 한 칸(11/12 실기 「월 봄P」)
    out = []
    for part in re.split(r'(\$[nN])', t):
        if re.fullmatch(r'\$[nN]', part or '') or not part:
            out.append(part); continue
        bullet = part[:1] in '·・'
        head, body = (part[0], part[1:]) if bullet else ('', part)
        # 줄 첫머리 빈칸(이름 줄 들여쓰기 「 월 봄」)은 그대로 둔다(11/12 실기: v0.1.30부터 반각 빈칸이 사라져 「월 봄」이 칸 왼쪽에 붙음)
        lead = body[:len(body) - len(body.lstrip(' '))]
        head, body = head + lead, body[len(lead):]
        # 낱말: 빈칸 또는 쉼표·마침표 뒤에서 나눔. (낱말, 앞에 빈칸 있었나)
        toks = []
        for i, w in enumerate(body.split(' ')):
            for j, piece in enumerate(re.split(r'(?<=[,.])(?=\S)', w)):
                if piece: toks.append((piece, i > 0 and j == 0))
        lines, cur = [], ''
        for piece, sp in toks:
            cand = cur + (' ' if sp and cur else '') + piece
            if cur and vis(cand) > W:
                lines.append(cur); cur = piece
            else:
                cur = cand
        lines.append(cur)
        out.append(head + '$n　'.join(lines))
    return ''.join(out)


def punct_space(t):
    """마침표·쉼표는 칸 왼쪽 끝 글리프 → 바로 뒤 공백 한 칸을 뺀다(대사 drop_space_after_punct와 같음, 줄바꿈 뒤에 적용)."""
    return re.sub(r'([.,．，])[ 　]', r'\1', t)


def tokens(t):
    """대사 문자열 → [('c', 글자) | ('k', 제어 번호) | ('p', 자동 조사 번호)]."""
    for k, forms in enumerate(PARTICLES):
        for f in forms: t = t.replace(f, chr(0xE000 + k))
    out, i = [], 0
    while i < len(t):
        if t[i] == '{' and re.match(r'\{[0-9A-F]{2}\}', t[i:i+4]):
            out.append(('k', int(t[i+1:i+3], 16))); i += 4
        elif 0xE000 <= ord(t[i]) < 0xE000 + len(PARTICLES):
            out.append(('p', ord(t[i]) - 0xE000)); i += 1
        else:
            out.append(('c', t[i])); i += 1
    return out


def drop_space_after_punct(tk):
    """마침표·쉼표 글리프는 칸 왼쪽 끝에 붙어 칸 오른쪽이 이미 비어 있음 → 바로 뒤 공백 한 칸을 빼야 띄어쓰기 한 번으로 보인다.
    줄바꿈은 공백을 센 채로 먼저 끝냈으므로 꺾는 자리는 그대로다."""
    out = []
    for x in tk:
        if x[0] == 'c' and x[1] in ' 　' and out and out[-1][0] == 'c' and dlg_char(out[-1][1]) in ('．', '，'):
            continue
        out.append(x)
    return out


# 줄바꿈으로 떼면 어색한 자리(11/12 사용자: 「안 / 해도 돼」, 「드렸나 / 봐요」): 그 빈칸은 꺾지 않는다
NO_BREAK_AFTER = {'안', '못', '잘', '좀', '더', '꼭', '또', '다', '새', '한', '두', '세', '네', '몇', '첫', '옛', '딴',
                  '이', '그', '저', '이런', '그런', '저런', '어떤', '무슨', '너무', '아주', '가장', '제일', '매우'}
AUX_START = re.compile(r'^(봐|봤|보다|본다|보네|보군|보구나|봅니다|보지)')


def glue_spaces(tk):
    """꺾으면 안 되는 빈칸을 U+00A0(빈칸 한 칸, 줄바꿈 안 함)으로 바꾼다."""
    def word(j, step):
        s = ''
        while 0 <= j < len(tk):
            k, v = tk[j]
            if k == 'c' and v not in ' 　 ': s = (s + v) if step > 0 else (v + s)
            elif k == 'k' and v in (1, 2, 3, 4): pass                # 색 코드는 낱말 안
            else: break
            j += step
        return s
    out = list(tk)
    for j, (k, v) in enumerate(tk):
        if k == 'c' and v == ' ':
            prev, nxt = word(j - 1, -1), word(j + 1, 1)
            if not prev or not nxt: continue
            if prev in NO_BREAK_AFTER or (AUX_START.match(nxt) and prev[-1] in '나가지'):
                out[j] = ('c', ' ')
    return out


def wrap(tk, width, col=0):
    """단어 단위로 꺾어 공백 자리에 {05}를 넣는다. (토큰, 끝 칸)"""
    tk = glue_spaces(tk)
    def is_sp(x): return x[0] == 'c' and x[1] in ' 　'
    def word_len(j):
        n = 0
        while j < len(tk) and not is_sp(tk[j]):
            k, v = tk[j]
            if k == 'k':
                if v in (5, 6, 7): break
                if v == 0x0A: n += NAMELEN
            else: n += 2 if k == 'p' else 1
            j += 1
        return n
    out = []
    for j, x in enumerate(tk):
        k, v = x
        if is_sp(x):
            if col > 0 and col + 1 + word_len(j + 1) > width:
                out.append(('k', 5)); col = 0
            elif col == 0:
                continue                                   # 줄 첫머리 공백은 버림
            else:
                out.append(x); col += 1
            continue
        if k == 'k':
            if v in (5, 6, 7): col = 0
            elif v == 0x0A: col += NAMELEN
            out.append(x); continue
        if col >= width: col = 0
        out.append(x); col += 2 if k == 'p' else 1
    return out, col


# ---------------------------------------------------------------- 글꼴
def render(ch, font):
    im = Image.new('L', (8, 16))
    ImageDraw.Draw(im).text((0, 0), ch, font=font, fill=255)
    body = im.crop((0, 1, 8, 12)).point(lambda p: 255 if p > 127 else 0)
    # 11/12 v0.1.27에 1px 오른쪽으로 옮겼다가 사용자 지시로 되돌림(0번 열부터)
    cell = Image.new('L', (8, 16)); cell.paste(body, (0, 2))
    out = bytearray()
    for y in range(16):
        v = 0
        for x in range(8):
            if cell.getpixel((x, y)): v |= 3 << (2 * x)
        out += struct.pack('<H', v)
    return bytes(out)


def render_left(ch, font):
    """render와 같되 잉크를 칸 왼쪽 끝(x=0)에 붙인다."""
    g = render(ch, font)
    rows = [struct.unpack_from('<H', g, 2 * y)[0] for y in range(16)]
    cols = [x for x in range(8) if any((r >> (2 * x)) & 3 for r in rows)]
    sh = min(cols) if cols else 0
    return b''.join(struct.pack('<H', r >> (2 * sh)) for r in rows)


def render_right(ch, font):
    """render와 같되 잉크를 칸 오른쪽 끝(x=7)에 붙인다."""
    g = render(ch, font)
    rows = [struct.unpack_from('<H', g, 2 * y)[0] for y in range(16)]
    cols = [x for x in range(8) if any((r >> (2 * x)) & 3 for r in rows)]
    sh = 6 - max(cols) if cols else 0          # 오른쪽 1px 여백(11/12 사용자: 여는 따옴표가 뒷글자에 붙음)
    return b''.join(struct.pack('<H', (r << (2 * sh)) & 0xFFFF) for r in rows)


# 壱·弐: 원본 글꼴에서는 네모 안 1·2 아이콘(대회 안내창 상금 순위). 그 코드(0x88EB·0x93F3)는 한글 「놀」「튄」이 쓰므로
# 비어 있는 코드 0x81F5(†)·0x81F6(‡)에 원본 아이콘 글리프를 복사해 쓴다(SUBST로 壱→†, 弐→‡)
ICON = {0x81F5: 0x88EB, 0x81F6: 0x93F3}


def build_font(rom, alloc, need_codes):
    orig = struct.unpack_from('<%dH' % g.NGLYPH, rom, CODES)
    oidx = {c: i + 1 for i, c in enumerate(orig)}
    keep = [c for c in orig if c >> 8 <= 0x87]
    hangul = [code_of(c) for c in N.ORDER]
    extra = sorted(c for c in need_codes if c not in oidx and c not in set(hangul))
    codes = sorted(set(keep) | set(extra) | set(hangul))
    assert len(codes) == len(set(codes))
    font = ImageFont.truetype(FONT, 12)
    rev = {code_of(c): c for c in N.ORDER}
    # 마침표·쉼표: 원래 전각 글리프는 칸 가운데라 한글 뒤에서 멀어 보임 → 갈무리로 그려 칸 왼쪽 끝에 붙임
    left = {0x8144: '.', 0x8143: ','}
    # 작은따옴표: 원본 ‘’는 같은 세로 막대라 열고 닫는 게 구별 안 됨(11/12 실기) → 갈무리 ‘(6 모양)은 칸 오른쪽, ’(9 모양)은 칸 왼쪽에 붙임
    left[0x8166] = '’'
    right = {0x8165: '‘'}
    # 영문·숫자: 원래 전각 글리프는 한글과 높이·위치가 안 맞음 → 갈무리 반각 글자로 다시 그림(ASCII 1바이트도 이 칸을 씀)
    galm = {0x824F + i: chr(0x30 + i) for i in range(10)}
    galm.update({0x8260 + i: chr(0x41 + i) for i in range(26)})
    galm.update({0x8281 + i: chr(0x61 + i) for i in range(26)})
    data = bytearray(32)
    blank = []
    for c in codes:
        if c in right:
            data += render_right(right[c], font)
        elif c in left:
            data += render_left(left[c], font)
        elif c in galm:
            data += render(galm[c], font)
        elif c in ICON:
            data += rom[GLYPHS + oidx[ICON[c]] * 32: GLYPHS + oidx[ICON[c]] * 32 + 32]
        elif c in oidx and c >> 8 <= 0x87:
            data += rom[GLYPHS + oidx[c] * 32: GLYPHS + oidx[c] * 32 + 32]
        else:
            ch = rev.get(c) or bytes([c >> 8, c & 255]).decode('cp932')
            gl = render(ch, font)
            if not any(gl) and ch not in ' 　': blank.append(ch)
            data += gl
    assert not blank, ('갈무리에 없는 글자', blank)
    gidx = {c: i + 1 for i, c in enumerate(codes)}
    blk = alloc.put(struct.pack('<H', len(codes)) + bytes(data), 4)      # 개수(u16) 바로 뒤에 글리프(원래 배치와 같음)
    gaddr, caddr = blk + 2, alloc.put(struct.pack('<%dH' % len(codes), *codes))
    for o, old in CTX_LITS:
        assert u32(rom, o) == old, hex(o)
    for o, v in zip([x for x, _ in CTX_LITS], [gaddr, caddr, blk] * 2):
        struct.pack_into('<I', rom, o, 0x08000000 + v)
    # 글꼴 B(작은 창 본문 등, 문맥 0x030013D0)는 한글이 없어 빈칸이 됨 → 글꼴 A를 같이 쓰게
    for o, old, v in [(0x4C98, 0x083F659E, gaddr), (0x4C9C, 0x083F831E, caddr), (0x4CA0, 0x083F84F4, MAP1), (0x4CA4, 0x083F659C, blk)]:
        assert u32(rom, o) == old, hex(o)
        struct.pack_into('<I', rom, o, 0x08000000 + v)
    # 평문 1바이트 표: 원래 가리키던 코드를 새 번호로
    m1 = list(struct.unpack_from('<256H', rom, MAP1))
    for b in range(256):
        if 1 <= m1[b] <= g.NGLYPH:
            c = orig[m1[b] - 1]
            m1[b] = gidx.get(c, 0)
    struct.pack_into('<256H', rom, MAP1, *m1)
    return codes, gidx, extra


# ---------------------------------------------------------------- 대사
def small_windows():
    """대사가 찍히는 작은 창 → {대사 위치: (글자 폭, 줄 수)}. 주소상 바로 앞의 창 명령을 따른다.
    - 8E(x, y, w, h, 1): 글자 창 = 그 폭, 줄 수 h/2 (0x800D328)
    - 7C(x, y, w, h, 1): 테두리를 그리고 글자 창은 안쪽 (x+1, y+1, w-2, h-2) (0x800C174)
    - 8D: 기본 대사창으로 되돌림(0x800D2E0) → 목록에 넣지 않음(대사 폭−1 사용)
    같은 함수(25 복귀·23 점프·4B로 끊김) 안에서만 찾는다."""
    seen = S.trace(); ps = sorted(seen); d = S.d; out = {}
    for i, p in enumerate(ps):
        if seen[p][0] != 0x99: continue
        for j in range(i - 1, max(0, i - 80), -1):
            op = seen[ps[j]][0]
            if op in (0x25, 0x23, 0x4B, 0x8D): break
            if op in (0x8E, 0x7C):
                args = [d[ps[k] + 1] for k in range(j - 1, j - 6, -1) if seen[ps[k]][0] == 2]
                if len(args) == 5:
                    _, h, w, y, x = args
                    out[p + 1] = (w, max(1, h // 2)) if op == 0x8E else (w - 2, max(1, (h - 2) // 2))
                break
    return out


DLG_RENDER = {}     # 대사 id → [번역, 롬에 넣는 최종 글(빌드 줄바꿈·빈칸 처리 뒤)]


def tk_str(tk):
    return ''.join(v if k == 'c' else ('{%02X}' % v if k == 'k' else '{P%d}' % v) for k, v in tk)


def dlg_drift():
    """회귀 검사(대사): 직전 빌드와 비교해 번역은 같은데 롬에 넣는 글(줄바꿈 {05} 자리·앞 빈칸 등)이 바뀐 대사.
    11/13 반성: 분류·줄바꿈 도구를 고치면 사용자가 화면 보고 맞춘 줄이 말없이 바뀐다. 평문 text_drift 와 달리
    목록이 있으면 빌드를 멈추고, 기준 파일은 통과(또는 --accept-drift)할 때만 새로 쓴다."""
    p = os.path.join(ROOT, 'build', 'dlg_render.json')
    old = json.load(open(p, encoding='utf-8')) if os.path.exists(p) else None
    drift = [] if old is None else [(i, repr(old[i][1]), '→', repr(v[1])) for i, v in DLG_RENDER.items()
                                    if i in old and old[i][0] == v[0] and old[i][1] != v[1]]
    return p, old is None, drift


def dialogue(rom, alloc, jp2ko, dlg, gidx):
    # 1바이트 칸 고르기: 짧은 대사(제자리) 글자 먼저, 그다음 빈도
    freq, short = collections.Counter(), collections.Counter()
    for e in dlg:
        for k, v in tokens(e['ko']):
            if k == 'c' and v not in SPACES:
                freq[dlg_char(v)] += 1
                if e['bytes'] - 1 < 6 or int(e['id'], 16) in NO_JUMP: short[dlg_char(v)] += 1
    # 2바이트 번호(0x7FF)를 넘는 글자는 1바이트 칸에만 넣을 수 있으니 맨 앞에
    over = [c for c, _ in freq.most_common() if gidx[code_of(c)] > 0x7FF]
    order = over + [c for c, _ in short.most_common() if c not in over] + \
        [c for c, _ in freq.most_common() if c not in short and c not in over]
    assert len(over) + len([c for c in short if c not in over]) <= PBYTE - 3, '1바이트 칸 부족'
    one = order[:PBYTE - 3]                                 # 03~F2, F3~F7은 자동 조사
    bm = list(struct.unpack_from('<248H', rom, BYTEMAP))
    bmap = {}
    for i, c in enumerate(one):
        b = 3 + i; bm[b] = gidx[code_of(c)] - 1; bmap[c] = b
    for k in range(len(PARTICLES)): bm[PBYTE + k] = 0xFFEF + k
    bm[SPACE] = gidx[0x8140] - 1
    struct.pack_into('<248H', rom, BYTEMAP, *bm)

    def enc(tk, force2=()):
        out = bytearray()
        for j, (k, v) in enumerate(tk):
            if k == 'k': out += bytes([1, v]); continue
            if k == 'p': out.append(PBYTE + v); continue
            if v in SPACES: out.append(SPACE); continue
            c = dlg_char(v)
            if c in bmap and j not in force2: out.append(bmap[c]); continue
            gi = gidx[code_of(c)]
            assert gi <= 0x7FF, ('대사 2바이트 번호 넘침', c, gi)
            out += bytes([0xF8 + (gi >> 8), gi & 0xFF])
        return bytes(out)

    stat = collections.Counter(); fails = []; short_jumps = []; pending = []; holes = []
    smallw = small_windows()
    prev_end, prev_col = None, 0
    for e in sorted(dlg, key=lambda e: int(e['id'], 16)):
        off = int(e['id'], 16); n = e['bytes'] - 1; end = off + n
        assert rom[end] == 0, hex(off)
        tk = tokens(e['ko'])
        if e['kind'] == 'line':
            col0 = prev_col if prev_end is not None and 0 < off - prev_end <= 8 else 0
            # 사이 명령이 23(새 글 시작, 예: 파일 메뉴 설명 `23 xx 00 00 99`)이면 앞 글에 이어지지 않음(11/11 실기)
            if col0 and rom[prev_end] in (0x23, 0x25, 0x95): col0 = 0   # 95 = 줄바꿈 명령(11/12 세이브 덮어쓰기 창), 25 = 상점 한 줄 문구 사이(11/12 실기: 「틀림없어요!」만 보임)
            # 사이에 98(창 비우기로 보임)이 있으면 새 화면에서 시작(11/12 실기: 4C008A 「오늘」만 첫 줄에 남음)
            if col0 and 0x98 in rom[prev_end:off]: col0 = 0
            # 일반 대사창은 엔진이 한 칸 먼저 꺾음(23칸 창에 22칸) → 폭−1. 작은 창은 그 창 폭(머리글 14자가 14칸 창에 들어감)
            tk, col = wrap(tk, smallw[off][0] if off in smallw else e['width'] - 1, col0)
            last = [v for k, v in tk if k == 'k']
            prev_col = col if not (tk and tk[-1][0] == 'k' and tk[-1][1] in (5, 6, 7)) else 0
        else:
            prev_col = 0
        prev_end = end + 1
        tk = drop_space_after_punct(tk)
        DLG_RENDER[e['id']] = [e['ko'], tk_str(tk)]
        b = enc(tk)
        if len(b) == n:
            rom[off:end] = b; stat['같은 길이'] += 1
        elif len(b) + 6 <= n:
            rom[off:off+len(b)+6] = b + b'\x01\xfd' + struct.pack('<I', 0x08000000 + end); stat['제자리'] += 1
            holes.append((off + len(b) + 6, end))                 # 되돌아가기 뒤는 읽히지 않음
        elif n >= 6 and off not in NO_JUMP:
            pending.append((off, b + b'\x01\xfd' + struct.pack('<I', 0x08000000 + end), 'FE'))
            holes.append((off + 6, end)); stat['옮김'] += 1
        elif len(b) > n and n >= 3:
            # 짧은 건너뛰기: 01 FC 번호(표 SHORT_JUMPS) + 남는 칸은 공백(건너뛰어 읽히지 않음)
            short_jumps.append(None)
            pending.append((off, b + bytes([1, 0xFD]) + struct.pack('<I', 0x08000000 + end), len(short_jumps) - 1))
            rom[off:end] = bytes([1, 0xFC, len(short_jumps) - 1]) + bytes([SPACE]) * (n - 3)
            stat['짧은 건너뛰기'] += 1
        else:
            diff = n - len(b)
            if diff < 0:
                fails.append((e['id'], e['jp'], e['ko'], len(b), n)); continue
            if diff % 2:
                ones = [j for j, (k, v) in enumerate(tk) if k == 'c' and v not in SPACES and dlg_char(v) in bmap and gidx[code_of(dlg_char(v))] <= 0x7FF]
                if ones: b = enc(tk, {ones[-1]})
                else: b = b[:-2] + bytes([SPACE]) + b[-2:] if len(b) >= 2 and b[-2] == 1 else b + bytes([SPACE])
                diff = n - len(b)
            b += b'\x01\x04' * (diff // 2)
            assert len(b) == n, (e['id'], len(b), n)
            rom[off:end] = b; stat['짧은 대사 맞춤'] += 1
    # 옮길 대사를 빈칸(다른 대사가 옮겨지며 남긴 원래 자리)에 큰 것부터 가장 잘 맞게 채우고, 남는 건 빈 구역에
    for a, b in holes: alloc.add(a, b)
    for off, data, kind in sorted(pending, key=lambda x: -len(x[1])):
        a = alloc.put(data, 1)
        if kind == 'FE': rom[off:off+6] = b'\x01\xfe' + struct.pack('<I', 0x08000000 + a)
        else: short_jumps[kind] = a
    stat['빈칸 합'] = sum(b - a for a, b in holes)
    assert len(short_jumps) <= 256
    return stat, fails, one, short_jumps


# ---------------------------------------------------------------- 평문 SJIS
REGIONS = json.load(open(os.path.join(ROOT, 'manifests', 'region-map.json'), encoding='utf-8'))['regions']
REG_START = [int(r['start'], 16) for r in REGIONS]


def real_ref(rom, r):
    """포인터 목록 중 진짜 포인터만: 표·코드·텍스트 구역, 또는 무압축 구역에서 앞뒤 칸도 롬 포인터(포인터 표 모양).
    압축 그림·소리·스크립트 속에서 우연히 같은 값이 나온 것은 고치지 않는다."""
    import bisect
    t = REGIONS[bisect.bisect_right(REG_START, r) - 1]['type']
    if t in ('table', 'code', 'text'): return True
    if t == 'raw-gfx':
        isp = lambda o: 0 <= o < 0x800000 - 3 and 0x08000000 <= u32(rom, o) < 0x08800000
        return isp(r - 4) or isp(r + 4)
    return False


def sjis(rom, alloc, raw):
    allstr = json.load(open(os.path.join(TR, 'sjis-all.json'), encoding='utf-8'))
    info = {int(x['off'], 16): x for x in allstr['strings']}
    # 진짜 포인터가 하나도 없는 「문자열」은 그림 속 가짜 포인터로 잡힌 꼬리 조각이라 시작점으로 치지 않는다
    real = {o for o, x in info.items() if any(real_ref(rom, int(r, 16)) for r in x['refs'])}
    starts = sorted(real | {int(x['off'], 16) for x in allstr['unreferenced']})
    import bisect
    stat = collections.Counter(); fails = []
    plan = []
    recs = {x['id'] for x, _ in raw if x.get('record')}
    for x, ko in raw:
        b = sjis_bytes(raw_text(x, ko))
        for w in x['where']:
            o = int(w, 16)
            if any(a <= o < z for a, z in SKIP_RANGES): stat['격자 구역 건너뜀'] += 1; continue
            plan.append((o, b, x['id'], ko))
    # 다른 문자열 안에 든 시작점(꼬리 공유) 찾기 — 길이·겹침은 원본 기준
    org = bytes(rom[:0x800000])
    keys = {int(k['off'], 16) for k in allstr['strings']
            if any(gp.split(':')[0] in '123' for gp in k['groups'])}   # 얼굴·큰 그림·배경 키만(묶음 7의 일본어는 스테이지 이름 = 파츠 표와 같게 바꿔야 함)
    for o, b, i, ko in plan:
        if o in keys:
            # 키와 화면 글이 같은 주소(예: 0x31A420 フェニックス = 큰 그림 키 2:10 + 로보 이름 6:29):
            # 키는 그대로 두고 화면용 묶음(0·4·5·6) 표 칸만 새 문자열로
            gs = [gp for gp in info[o]['groups'] if gp.split(':')[0] not in '1237']
            if gs:
                a = alloc.put(b + bytes(1), 1)
                for gp in gs:
                    g_, ix = map(int, gp.split(':'))
                    ent = u32(rom, S.STR_GROUPS + 4 * g_) - 0x08000000 + 4 * ix
                    assert u32(rom, ent) == 0x08000000 + o
                    struct.pack_into('<I', rom, ent, 0x08000000 + a)
            stat['키 겸용 문자열(키는 그대로)'] += 1
            continue
        L = org.index(0, o) - o
        k = bisect.bisect_right(starts, o)
        inner = k < len(starts) and starts[k] < o + L
        k2 = bisect.bisect_left(starts, o)
        outer = k2 > 0 and org.find(0, starts[k2-1], o) < 0      # 앞 문자열이 o까지 이어짐
        refs0 = [int(r, 16) for r in info[o]['refs']] if o in info else []
        refs = [r for r in refs0 if real_ref(rom, r)]
        stat['가짜 포인터 뺌'] += len(refs0) - len(refs)
        if o in info and o not in real and outer:
            stat['가짜 꼬리 조각 건너뜀'] += 1; continue
        if len(b) <= L and not inner and not outer:
            rom[o:o+L] = b + bytes(L - len(b)); stat['제자리'] += 1
        elif refs:
            a = alloc.put(b + b'\0', 1)
            for r in refs:
                assert u32(rom, r) == 0x08000000 + o, ('포인터 아님', hex(r), hex(o))
                struct.pack_into('<I', rom, r, 0x08000000 + a)
            stat['옮김'] += 1
        elif i in recs and not inner and not outer and len(org[o + L:o + len(b) + 2]) == len(b) + 2 - L \
                and not any(org[o + L:o + len(b) + 2]):
            # 레코드 안 이름 칸(지도 지점 표 등): 포인터가 없지만 원문 뒤가 0으로 비어 있으면 그 안에서 늘린다
            # (끝 0 하나 + 여유 0 하나까지 원본이 비어 있어야 함. 11/12 「어둠의 배틀장」 지도 메뉴)
            rom[o:o + len(b) + 1] = b + b'\0'; stat['레코드 칸 안에서 늘림'] += 1
        else:
            fails.append((i, hex(o), ko, len(b), L, 'inner' if inner else 'outer' if outer else '길이'))
    # 같은 원문이 where 밖(파츠·스테이지·배틀 표, 지도 장소 표 등)에도 있다: 게임이 이름으로 찾으므로 롬 모든 곳을 같게.
    # 단, 얼굴·큰 그림·배경 키(묶음 1·2·3)와 같은 원문은 일본어 짝 표가 있으므로 통째로 건드리지 않는다
    # (키만 바꾸면 「人物[..]が見つからない」, 표만 바꿔도 같은 오류).
    import bisect as _b
    done = {o for o, _, _, _ in plan}
    keys = {int(k['off'], 16) for k in allstr['strings']
            if any(gp.split(':')[0] in '123' for gp in k['groups'])}   # 얼굴·큰 그림·배경 키만(묶음 7의 일본어는 스테이지 이름 = 파츠 표와 같게 바꿔야 함)
    keytext = {k['jp'] for k in allstr['strings'] if any(gp.split(':')[0] in '23' for gp in k['groups'])}   # 묶음 1(인물)은 face_keys가 같이 바꿈
    # 키와 같은 원문(ユウスケ·フェニックス·バトルタワー 등 6종)은 파츠 레코드 구역과 지도 지점 표에서만 바꾼다
    KEYTEXT_OK = [(0x6A0000, 0x6C0000), (0x7B7400, 0x7B8C00), (0x7C5000, 0x7C6800)]
    for x, ko in raw:
        pat = x['jp'].encode('cp932')
        if len(pat) < 4: continue
        b = sjis_bytes(punct_space(ko)); p = 0
        while True:
            p = org.find(pat, p)
            if p < 0: break
            t = REGIONS[_b.bisect_right(REG_START, p) - 1]['type']
            if (org[p + len(pat)] == 0 and org[p - 1] < 0x20 and p not in done and p not in keys and t in ('text', 'table')
                    and not any(a <= p < z for a, z in SKIP_RANGES)
                    and (x['jp'] not in keytext or any(a <= p < z for a, z in KEYTEXT_OK))):
                if len(b) <= len(pat):
                    rom[p:p+len(pat)] = b + bytes(len(pat) - len(b)); stat['같은 원문 다른 자리'] += 1
                else:
                    fails.append((x['id'], hex(p), ko, len(b), len(pat), '다른 자리 길이'))
            p += 1
    return stat, fails


# 배경 키(묶음 3)를 장소 이름으로도 쓰는 곳: `05 배경키 / 05 묶음3 장소 / AE`. 두 번째(장소 이름)만 새 한국어 문자열(묶음 5 뒤에 붙임)로
KEY_PLACE = {0x3007: '니카이도의 방', 0x3009: '라운지', 0x301E: '내 방', 0x300A: '거실', 0x3008: '배틀 타워'}   # 自分の部屋=내 방(사용자 10/30)


def place_names(rom, alloc):
    g5 = S.STR_GROUPS + 4 * 5
    old = u32(rom, g5) - 0x08000000
    ents = [u32(rom, old)]                                   # 묶음 5의 원래 칸 1개(アイテム０)
    newsid = {}
    for k, ko in KEY_PLACE.items():
        newsid[k] = 0x5000 | len(ents)
        ents.append(0x08000000 + alloc.put(sjis_bytes(ko) + bytes(1), 1))
    struct.pack_into('<I', rom, g5, 0x08000000 + alloc.put(struct.pack('<%dI' % len(ents), *ents)))
    seen = S.trace(); ps = sorted(seen); n = 0
    for i, p in enumerate(ps):
        if seen[p][0] != 0xAE or i < 2: continue
        q1, q2 = ps[i - 2], ps[i - 1]
        if seen[q1][0] == 5 and seen[q2][0] == 5:
            sid = rom[q2+1] | rom[q2+2] << 8
            if sid in newsid:
                struct.pack_into('<H', rom, q2 + 1, newsid[sid]); n += 1
    # 메뉴 항목으로도 키를 그대로 쓰는 곳: `05 키 / 02 xx / 02 01 / 80`(로보 스테이션 메뉴 「ラウンジ」, 11/12 실기)
    for i, p in enumerate(ps):
        if seen[p][0] != 5 or i + 3 >= len(ps): continue
        sid = rom[p+1] | rom[p+2] << 8
        if sid in newsid and [seen[q][0] for q in ps[i+1:i+4]] == [2, 2, 0x80]:
            struct.pack_into('<H', rom, p + 1, newsid[sid]); n += 1
    # 알림 「(장소)에 갈 수 있게 되었습니다!」: `05 키 / 0D 04`로 변수 칸에 담았다가 0C로 꺼내 찍음(50FD4C バトルタワー 1곳뿐, 11/13)
    for i, p in enumerate(ps):
        if seen[p][0] != 5 or i + 1 >= len(ps): continue
        sid = rom[p+1] | rom[p+2] << 8
        if sid in newsid and seen[ps[i+1]][0] == 0x0D:
            struct.pack_into('<H', rom, p + 1, newsid[sid]); n += 1
    return n


# 스크립트 피연산자 1바이트 고침 {위치: (원본, 새 값)}
# 0x505D70: 종합 성적 「제N 시합 … ＝」의 ＝ 가로 위치(`02 09 / 06 00 00 / 02 02 / 11 / 90` = 커서 (9, 줄*2)).
#   한국어 「토털 스코어」 줄은 맨 앞 전각 빈칸이 줄 첫머리에서 빠져 ＝가 8칸 → 시합 줄도 8로(11/13 사용자 「토털 스코어 ＝랑 맞게」)
SCRIPT_BYTES = {0x505D70: (0x09, 0x08)}

PART_NAME_CNT, PART_NAME_TAB =0xFDA8, 0xFDAC   # 파츠 이름 찾기(0x800FD50·0x800FDB0, strcmp)가 쓰는 분류별 개수·이름 표 포인터


def part_keys(rom):
    """그림 키(묶음 2) 중 원문이 파츠 이름과 같은 것(フェニックス 0x200A)을 빌드된 파츠 이름 바이트로 제자리에서 바꾼다.
    스크립트가 이 키를 파츠 이름으로도 넘기는데 파츠 표는 한국어라 찾기에 실패 → 「パーツのカテゴリ番号が不正」 멈춤
    (11/13 로보 한정 배틀 레벨 4 = 라이트닝 스카이어형). 그림 표 0x3E3Fxx도 같은 주소를 가리켜 제자리면 짝이 맞는다."""
    org = S.d
    def names(r):
        cnt = u32(r, PART_NAME_CNT) - 0x08000000; tab = u32(r, PART_NAME_TAB) - 0x08000000; out = []
        for c in range(7):
            arr = u32(r, tab + 4 * c) - 0x08000000
            for j in range(r[cnt + c]):
                a = u32(r, arr + 4 * j) - 0x08000000
                out.append(bytes(r[a:r.index(0, a)]))
        return out
    jp2ko_part = dict(zip(names(org), names(rom)))
    g2 = u32(org, S.STR_GROUPS + 8) - 0x08000000; n = 0
    for i in range(0x40):
        a = u32(org, g2 + 4 * i) - 0x08000000
        if not (0 <= a < 0x800000): break
        jp = org[a:org.index(0, a)]
        ko = jp2ko_part.get(jp)
        if ko and ko != jp:
            assert len(ko) <= len(jp), ('파츠 키 길이', jp)
            rom[a:a + len(jp)] = ko + bytes(len(jp) - len(ko)); n += 1
    return n


# 인물 키를 화자 이름과 다르게 넣을 것: 대회 대사 「결승 상대는 (키) 씨입니다」에 키가 그대로 들어가
# 「이케다 선생님 씨」가 됨(11/12 실기) → 키는 이름표용 「이케다 선생」(11/12 사용자: 이름표는 「이케다 선생」,
# 대사 속 아이들 호칭은 「이케다 선생님」 그대로). 사용자 지시로 띄어 씀(face_keys가 전각 빈칸으로 바꿈).
KEY_KO = {'イケダ先生': '이케다 선생'}


def face_keys(rom, alloc, jp2ko):
    """인물 키(묶음 1): 대전 상대 이름 칸 등이 키 문자열을 그대로 화면에 찍는다(「COMMANDER ユウスケ」).
    인물 표 0x3E3E74(54칸)는 묶음 1과 같은 주소를 가리키고, 찾기는 선형 탐색(linear_search)이라 제자리에서 바꾸면 짝이 맞는다.
    번역은 대사 화자 이름(「이름{05}」) → 용어집. 그림자·변형 얼굴 키(影·普段·仮面 등)와 번역 없는 것은 그대로.
    자리를 넘으면 새 자리에 두고 이 주소를 가리키는 진짜 포인터(묶음 1 표·인물 표)를 모두 고친다."""
    gl = json.load(open(os.path.join(ROOT, 'work/glossary/glossary-ko.json'), encoding='utf-8'))
    gl = dict(gl) if isinstance(gl, list) else gl.get('terms', gl)
    allstr = json.load(open(os.path.join(TR, 'sjis-all.json'), encoding='utf-8'))
    refs = {int(x['off'], 16): [int(r, 16) for r in x['refs']] for x in allstr['strings']}
    g1 = u32(rom, S.STR_GROUPS + 4) - 0x08000000
    stat = collections.Counter(); done = {}
    for i in range(54):
        a = u32(rom, g1 + 4 * i) - 0x08000000
        jp = S.d[a:S.d.index(0, a)].decode('cp932')
        ko = jp2ko.get(jp + '{05}')
        ko = re.sub(r'\{..\}', '', ko).strip() if ko else None
        if not ko and jp in gl: ko = gl[jp]['ko'] if isinstance(gl[jp], dict) else gl[jp]
        if not ko: stat['그대로'] += 1; continue
        ko = KEY_KO.get(jp, ko)
        # 대진표 이름 칸은 키를 2바이트 글자로만 읽음 → 반각 공백·영문(1바이트)이 있으면 한 바이트 어긋나 끝(00)을 놓치고
        # 뒤 문자열까지 찍힘(「이케다 선생님」 뒤에 「니카이도…」, 11/12 실기) → 전각으로 바꿔 넣는다
        ko = ''.join('　' if c == ' ' else dlg_char(c) for c in ko)
        b = sjis_bytes(ko); L = len(jp.encode('cp932'))
        assert len(b) % 2 == 0, ('인물 키 홀수 바이트', ko)
        if len(b) <= L:
            rom[a:a+L] = b + bytes(L - len(b)); stat['제자리'] += 1
        else:
            na = alloc.put(b + bytes(1), 1)
            rs = [r for r in refs.get(a, []) if real_ref(rom, r)] + [g1 + 4 * i]
            for r in set(rs):
                assert u32(rom, r) == 0x08000000 + a, hex(r)
                struct.pack_into('<I', rom, r, 0x08000000 + na)
            stat['옮김'] += 1
        done[jp] = ko
    return stat, done


def passwords(rom, alloc):
    stat = collections.Counter()
    for sid, b in N.passwords().items():
        ent = u32(rom, S.STR_GROUPS + 4 * (sid >> 12)) - 0x08000000 + 4 * (sid & 0xFFF)
        a = u32(rom, ent) - 0x08000000
        assert rom[a] == 0xFF
        p = a + 1
        while rom[p]: p += 2
        L = p + 1 - a
        if len(b) <= L: rom[a:a+L] = b + bytes(L - len(b)); stat['제자리'] += 1
        else:
            struct.pack_into('<I', rom, ent, 0x08000000 + alloc.put(b, 1)); stat['옮김'] += 1
    return stat


# ---------------------------------------------------------------- 훅
def dialogue_hook(rom, alloc):
    """0x800D520(`01 xx`, xx>0x0A): FE·FD = 다음 4바이트 주소로, FC = 다음 1바이트 번호의 짧은 건너뛰기 표로. 표 주소를 돌려준다."""
    sjtab = alloc.put(bytes(256 * 4))
    base = alloc.reserve(0x80)                                   # 훅 코드 자리(실제 길이보다 넉넉히)
    ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
    src = f'''
        cmp r1, #0xFE
        beq jump
        cmp r1, #0xFD
        beq jump
        cmp r1, #0xFC
        beq short
        adds r0, r5, #0
        ldr r2, =0x0800CD7D
        bl veneer
        b back
    short:
        ldrb r0, [r4]
        lsls r0, r0, #2
        ldr r2, =0x{0x08000000 + sjtab:08X}
        ldr r4, [r2, r0]
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
        ldr r0, =0x0800D4E1
        bx r0
    veneer:
        bx r2
    '''
    code = bytes(ks.asm(src, 0x08000000 + base)[0])
    assert len(code) <= 0x80; rom[base:base+len(code)] = code; a = base

    patch = bytes(ks.asm('ldr r0, [pc, #0]' + chr(10) + 'bx r0', 0x0800D520)[0]) + struct.pack('<I', 0x08000000 + a | 1)
    assert rom[0xD520:0xD528] == bytes.fromhex('281cfff72bfcdbe7')
    rom[0xD520:0xD528] = patch
    return sjtab


LATIN_JONG = {'L': 2, 'M': 1, 'N': 1, 'R': 2}
DIGIT_JONG = {'0': 1, '1': 2, '3': 1, '6': 1, '7': 2, '8': 2}


def jong_of(ch):
    """0=받침 없음, 1=받침, 2=ㄹ 받침."""
    if '가' <= ch <= '힣':
        t = (ord(ch) - 0xAC00) % 28
        return 0 if t == 0 else 2 if t == 8 else 1
    if ch in N.JAMO: return 0 if ch in N.V_LIST else 2 if ch == 'ㄹ' else 1
    h = chr(ord(ch) - 0xFEE0) if '！' <= ch <= '～' else ch
    return LATIN_JONG.get(h.upper(), DIGIT_JONG.get(h, 0))


def glyph_hook(rom, alloc, codes, gidx):
    """0x800CD2C(글자 하나 그리기, r0=창, r1=글자 번호) 앞에 끼운다: 마지막 글자 기억, 0xFFF0+k면 자동 조사."""
    rev = {code_of(c): c for c in N.ORDER}
    jt = bytearray(len(codes) + 1)
    for c, i in gidx.items():
        ch = rev.get(c) or bytes([c >> 8, c & 255]).decode('cp932')
        jt[i] = jong_of(ch)
    jtab = alloc.put(bytes(jt))
    part = bytearray()
    for outs in PART_OUT:
        for o in outs:
            gl = [gidx[code_of(c)] for c in o] + [0]
            part += struct.pack('<HH', gl[0], gl[1])
    ptab = alloc.put(bytes(part))
    base = alloc.reserve(0x100)                                  # 훅 코드 자리(실제 길이보다 넉넉히)
    ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
    src = f'''
    entry:
        push {{r4, r5, r6, r7, lr}}
        adds r6, r0, #0
        ldr r3, =0xFFF0
        cmp r1, r3
        bhs particle
        ldr r2, =0x{LAST:08X}
        strh r1, [r2]
        bl orig
        b done
    particle:
        subs r1, r1, r3
        cmp r1, #{len(PARTICLES)}
        bhs done
        ldr r2, =0x{LAST:08X}
        ldrh r2, [r2]
        movs r0, #0
        ldr r3, =0x{len(jt):X}
        cmp r2, r3
        bhs gotflag
        ldr r3, =0x{0x08000000 + jtab:08X}
        ldrb r0, [r3, r2]
    gotflag:
        lsls r2, r1, #1
        adds r2, r2, r1
        adds r2, r2, r0
        lsls r2, r2, #2
        ldr r3, =0x{0x08000000 + ptab:08X}
        adds r7, r3, r2
        ldrh r1, [r7]
        cmp r1, #0
        beq second
        ldr r2, =0x{LAST:08X}
        strh r1, [r2]
        adds r0, r6, #0
        bl orig
    second:
        ldrh r1, [r7, #2]
        cmp r1, #0
        beq done
        ldr r2, =0x{LAST:08X}
        strh r1, [r2]
        adds r0, r6, #0
        bl orig
    done:
        pop {{r4, r5, r6, r7}}
        pop {{r3}}
        bx r3
    orig:
        push {{r4, r5, lr}}
        adds r4, r0, #0
        adds r5, r1, #0
        ldrb r0, [r4, #2]
        ldr r2, =0x0800CD35
        bx r2
    '''
    code = bytes(ks.asm(src, 0x08000000 + base)[0])
    assert len(code) <= 0x100; rom[base:base+len(code)] = code; a = base

    assert rom[0xCD2C:0xCD34] == bytes.fromhex('30b5041c0d1ca078'), rom[0xCD2C:0xCD34].hex()
    rom[0xCD2C:0xCD34] = bytes.fromhex('004a1047') + struct.pack('<I', 0x08000000 + a | 1)
    return a


def linear_search(rom):
    """0x8000E54(표, 개수, 이름) → 번호|-1: 원래는 일본어 순으로 정렬된 이름 표의 2진 탐색(비교 0x8000DA4).
    번역하면 정렬이 깨져 「バトル[..]が見つからない」 → 같은 입출력의 선형 탐색으로 바꾼다(호출 9곳)."""
    ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
    src = '''
        push {r4, r5, r6, r7, lr}
        adds r5, r0, #0
        adds r6, r1, #0
        adds r7, r2, #0
        movs r4, #0
    loop:
        cmp r4, r6
        bge notfound
        lsls r0, r4, #2
        ldr r1, [r5, r0]
        adds r0, r7, #0
        bl 0x08000DA4
        cmp r0, #0
        beq found
        adds r4, #1
        b loop
    notfound:
        movs r4, #1
        rsbs r4, r4, #0
    found:
        adds r0, r4, #0
        pop {r4, r5, r6, r7}
        pop {r1}
        bx r1
    '''
    code = bytes(ks.asm(src, 0x08000E54)[0])
    assert len(code) <= 0x44 and rom[0xE54:0xE56] == bytes.fromhex('f0b5')
    rom[0xE54:0xE98] = code + bytes.fromhex('c046') * ((0x44 - len(code)) // 2)


def main(argv):
    rom = bytearray(open(SRC, 'rb').read())
    assert len(rom) == 0x800000
    alloc = Alloc(rom, FREE_REGIONS)
    jp2ko, raw, dlg = load()
    # 필요한 글자 코드(기호): 대사·평문·이름 입력 격자
    need = set()
    for e in dlg:
        for k, v in tokens(e['ko']):
            if k == 'c' and v not in SPACES: need.add(code_of(dlg_char(v)))
    for _, ko in raw:
        bb = sjis_bytes(ko); i = 0
        while i < len(bb):
            if bb[i] >= 0x80: need.add(bb[i] << 8 | bb[i+1]); i += 2
            else: i += 1
    codes, gidx, extra = build_font(rom, alloc, need)
    print('글꼴', len(codes), '자, 원래 글꼴에 없어 새로 그린 기호', ''.join(bytes([c >> 8, c & 255]).decode('cp932') for c in extra))
    linear_search(rom)
    sjtab = dialogue_hook(rom, alloc)
    glyph_hook(rom, alloc, codes, gidx)
    if '--no-name' not in argv:
        # 이름 입력 루틴은 한 덩어리(약 30KB)라 대사 조각보다 먼저 자리를 잡는다
        size = len(N.module(0x08000000)[0]); base = alloc.reserve(size + 16)
        n = N.patch(rom, 0x08000000 + base)
        print('이름 입력 루틴', hex(0x08000000 + base), n, '바이트')
    json.dump({'sjtab': sjtab}, open(os.path.join(ROOT, 'build', 'layout.json'), 'w'))
    if '--no-dialogue' not in argv:
        st, fails, one, sj = dialogue(rom, alloc, jp2ko, dlg, gidx)
        for i, a in enumerate(sj): struct.pack_into('<I', rom, sjtab + 4 * i, 0x08000000 + a)
        print('대사', dict(st), '실패', len(fails))
        for f in fails[:20]: print('  ', f)
        dp, first, ddrift = dlg_drift()
        print('번역은 그대로인데 롬 글(줄바꿈·빈칸)이 바뀐 대사', len(ddrift), '건 (직전 빌드와 비교%s)' % (', 기준 파일 처음 만듦' if first else ''))
        for f in ddrift[:60]: print('  ', *f)
        if ddrift and '--accept-drift' not in argv:
            raise SystemExit('대사 회귀 의심 %d건: 사용자 확인 뒤에만 --accept-drift 로 빌드' % len(ddrift))
        json.dump(DLG_RENDER, open(dp, 'w', encoding='utf-8'), ensure_ascii=False)
    if '--no-sjis' not in argv:
        st, fails = sjis(rom, alloc, raw)
        print('평문', dict(st), '실패', len(fails))
        for f in fails[:40]: print('  ', f)
        over = check_windows(raw)
        print('창 넘침 검사', len(over), '건 (창', len(WINDOWS), '종류)')
        for f in over: print('  ', *f)
        drift = text_drift(raw)
        print('번역은 그대로인데 화면 글이 바뀐 평문', len(drift), '건 (직전 빌드와 비교)')
        for f in drift[:40]: print('  ', *f)
        if over:
            raise SystemExit('창 넘침이 있어 롬을 쓰지 않음')
    print('비밀번호', dict(passwords(rom, alloc)))
    st, _ = face_keys(rom, alloc, jp2ko)
    print('인물 키', dict(st))
    print('장소 이름(키 겸용) 바꾼 곳', place_names(rom, alloc))
    print('파츠 이름과 같은 그림 키', part_keys(rom))
    for o, (a, b) in SCRIPT_BYTES.items():
        assert S.d[o] == a and rom[o] == a, ('스크립트 바이트 다름', hex(o))
        rom[o] = b
    print('스크립트 바이트 고침', len(SCRIPT_BYTES))
    if '--no-gfx' not in argv:
        import build_gfx
        print('그림', build_gfx.apply(rom, alloc))
    rom[0xBD] = (-(sum(rom[0xA0:0xBD]) + 0x19)) & 0xFF
    print('새 데이터', alloc.used, '바이트, 남은 빈 공간', alloc.left(), '바이트')
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, 'wb').write(rom)
    print('출력', OUT)


if __name__ == '__main__':
    main(sys.argv[1:])
