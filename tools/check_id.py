"""ID별 재번역 묶음 기계 검사: python tools/check_id.py 0 [1 2 ...]

- 묶음의 모든 ID가 번역됐는지(빠짐·남는 ID)
- 제어 코드 {xx}의 순서·개수가 원문과 같은지
- {0A}(주인공 이름) 바로 뒤에 받침 따라 바뀌는 조사가 붙었는지
- 글꼴에 없는 한글, 일본어(가나·한자)가 남았는지
- 말줄임표·물결표 뒤 마침표·쉼표, 이중 부호
- 사용자 고정 줄(locked)과 다른지
"""
import json, os, re, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TR = os.path.join(ROOT, 'work', 'translation')
FONT = set(open(os.path.join(ROOT, 'work', 'font', 'hangul_order.txt'), encoding='utf-8').read())
CODE = re.compile(r'\{[0-9A-F]{2}\}')
BAD_AFTER_NAME = re.compile(r'\{0A\}(?:\{04\})?(은|는|이|가|을|를|과|와|으로|로|이랑|랑|이야|야|아|이에요|예요|이다|냐|이냐|라는|이라는|라고|이라고|라면|이라면|여|이여)(?![가-힣(])')   # 은(는) 같은 자동 조사 꼴은 허용
JA = re.compile(r'[぀-ヿ一-鿿]')


def check(n):
    items = json.load(open(os.path.join(TR, 'idbatches', 'dlg-%03d.json' % n), encoding='utf-8'))
    p = os.path.join(TR, 'out-id', 'dlg-%03d.json' % n)
    tr = json.load(open(p, encoding='utf-8'))['translations']
    probs = []
    ids = [x['id'] for x in items]
    for i in ids:
        if i not in tr: probs.append((i, '번역 없음'))
    for i in tr:
        if i not in ids: probs.append((i, '묶음에 없는 ID'))
    for x in items:
        k = tr.get(x['id'])
        if k is None: continue
        # 줄바꿈 {05}를 번역에서 더 넣는 것은 허용(창이 좁아 손으로 꺾은 곳). 빼거나 다른 코드가 다르면 문제
        cj, ck = CODE.findall(x['jp']), CODE.findall(k)
        if ck.count('{05}') > cj.count('{05}'): ck = [c for c in ck if c != '{05}']; cj = [c for c in cj if c != '{05}']
        if cj != ck: probs.append((x['id'], '코드 다름', CODE.findall(x['jp']), CODE.findall(k)))
        m = BAD_AFTER_NAME.search(k)
        if m: probs.append((x['id'], '이름 뒤 조사', m.group(0)))
        m2 = re.search(r'\{0A\}(?:\{04\})?(이었|였|이지|이니|이군|이구나|구나|군|이네|네[.!?」]|지[.!?」]|이라|라서|이라서|이잖|잖|이에|예)', k)
        if m2: probs.append((x['id'], '이름 뒤 서술격', m2.group(0)))
        nf = sorted({c for c in k if '가' <= c <= '힣' and c not in FONT})
        if nf: probs.append((x['id'], '글꼴에 없는 한글', nf))
        ja = JA.findall(CODE.sub('', k).replace('壱', '').replace('弐', ''))   # 壱·弐은 원본 글꼴의 1·2 아이콘
        if ja: probs.append((x['id'], '일본어 남음', ja))
        if re.search(r'(…|~)[.,]', k): probs.append((x['id'], '말줄임·물결 뒤 부호'))
        if re.search(r'[.!?][.,]', k): probs.append((x['id'], '이중 부호'))
        if 'locked' in x and k != x['locked']: probs.append((x['id'], '고정 줄과 다름', x['locked'], k))
        if x['jp'].startswith('「') != k.startswith('「'): probs.append((x['id'], '여는 괄호 다름'))
        # 직역투 의심(korean-localization-style 14가지 중 기계로 잡히는 것) — 줄마다 다시 읽고 판단
        for pat, why in ((r'이 내가|이 나를|이 몸이 아닌', '이 내가(1인칭 강조)'), (r'대체', '대체(いったい)'),
                         (r'다들한테|다들에게', '다들한테'), (r'나 자신은|나 자신도|내 자신', '나 자신은(自身)'),
                         (r'이것을|그것을', '이것을/그것을'), (r'에 대해서야|에 대해 말해', '~에 대해')):
            if re.search(pat, k): probs.append((x['id'], '직역투 의심: ' + why, k[:40]))
    return len(items), probs


def main(args):
    for a in args:
        n, probs = check(int(a))
        print('묶음 %03d: %d줄, 문제 %d' % (int(a), n, len(probs)))
        for p in probs: print('  ', *p)


if __name__ == '__main__':
    main(sys.argv[1:])
