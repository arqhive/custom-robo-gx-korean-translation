"""번역 결과 기계 검사: python -X utf8 tools/check_batch.py [묶음이름...]

- 묶음의 모든 id가 번역됐는지
- 제어 코드({xx}, $X, #X, %s/%d)가 글자·개수·순서까지 같은지
- KS X 1001 밖 글자, 일본 가나·한자가 남았는지
- {0A} 바로 뒤 받침 따라 바뀌는 조사
- 말줄임표·물결표 뒤 마침표
- 고정 칸(max_cells) 넘침
- 용어집 이름: 원문에 용어집 원문이 있으면 번역에 그 한국어가 있는지(경고)
"""
import json, os, re, sys, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = os.path.join(ROOT, 'work/translation/batches')
O = os.path.join(ROOT, 'work/translation/out')
CODE = re.compile(r'\{[0-9A-Fa-f]{2}\}|\$[A-Za-z]|#[A-Z]|%[0-9]*[sd]')
CTRL = re.compile(r'\{..\}|\$[A-Za-z]|#[A-Z]')
JP = re.compile(r'[ぁ-んァ-ヶ一-龥]')
BAD_PARTICLE = re.compile(r'\{0A\}(은|는|이|가|을|를|와|과|이랑|랑|이야|야|으로|로)(?![가-힣])')
gloss = json.load(open(os.path.join(ROOT, 'work/glossary/glossary-ko.json'), encoding='utf-8'))
NAMES = sorted(((k, v['ko']) for k, v in gloss.items() if len(k) >= 3 and v.get('cat') in ('인물', '로보', '대회', '장소', '스테이지', '단체', '파츠', '가게', '배틀')), key=lambda x: -len(x[0]))


import sys as _sys
_sys.path.insert(0, os.path.dirname(__file__))
import gxtext as _g
# 원본 글꼴 A에 있는 기호(가나·한자 제외)는 그대로 쓸 수 있다(⑯⑰ 체크 상자 등)
FONT_SYMBOLS = {c for c in _g.CH if not JP.match(c)}


def ksx(c):
    if c in FONT_SYMBOLS: return True
    try: c.encode('euc-kr'); return True
    except UnicodeEncodeError: return False


def _desc_window(it):
    import build as _bd
    w = _bd.window_of(it)
    return bool(w and w['mode'] == 'desc' and it['jp'][:1] == '・')


def check(name):
    items = json.load(open(os.path.join(B, name + '.json'), encoding='utf-8'))
    path = os.path.join(O, name + '.json')
    if not os.path.exists(path): return ['결과 파일 없음'], 0
    res = json.load(open(path, encoding='utf-8'))
    tr = res.get('translations', {})
    probs = []
    ex_path = os.path.join(ROOT, 'work/translation/exclude.json')
    EXCL = json.load(open(ex_path, encoding='utf-8')) if os.path.exists(ex_path) else {}
    for it in items:
        k = it['id']; jp = it['jp']; ko = tr.get(k)
        if k in EXCL: continue  # 데이터 오독(빌드에서 뺌)
        if ko is None: probs.append(f'{k} 번역 없음'); continue
        # 줄바꿈 $N을 번역에서 더 넣는 것은 허용(도움말 등 손으로 꺾은 곳). 빼거나 다른 코드가 다르면 문제
        cj, ck = CODE.findall(jp), CODE.findall(ko)
        if ck.count('$N') > cj.count('$N'): cj = [c for c in cj if c != '$N']; ck = [c for c in ck if c != '$N']
        # 설명창(build.WINDOWS 'desc')은 빌드가 낱말 단위로 $n을 다시 넣으므로 $n 개수 차이는 문제 아님(11/12)
        if _desc_window(it): cj = [c for c in cj if c != '$n']; ck = [c for c in ck if c != '$n']
        if cj != ck: probs.append(f'{k} 코드 다름 {CODE.findall(jp)} → {CODE.findall(ko)}')
        if JP.search(ko): probs.append(f'{k} 일본 글자 남음: {ko[:40]}')
        bad = sorted({c for c in ko if ord(c) > 0x7F and not ksx(c)})
        if bad: probs.append(f'{k} 완성형 밖 글자 {bad}')
        if BAD_PARTICLE.search(ko): probs.append(f'{k} {{0A}} 뒤 조사: {ko[:50]}')
        if re.search(r'[…~〜]\.', ko): probs.append(f'{k} 말줄임표·물결표 뒤 마침표')
        mc = it.get('max_cells')
        if mc is not None and len(CTRL.sub('', ko)) > mc: probs.append(f'{k} 칸 넘침 {len(CTRL.sub("", ko))}>{mc}: {ko}')
        for jn, kn in NAMES:
            if jn in jp and kn not in ko:
                probs.append(f'{k} (경고) 용어 {jn}={kn} 없음: {ko[:50]}'); break
    return probs, len(items)


def main():
    names = sys.argv[1:] or sorted(f[:-5] for f in os.listdir(B) if f.endswith('.json'))  # 대괄호 경로라 glob 금지
    assert names, '묶음 0개'
    tot = 0
    for n in names:
        p, cnt = check(n)
        hard = [x for x in p if '(경고)' not in x]
        print(f'== {n}: {cnt}개, 문제 {len(hard)}, 경고 {len(p) - len(hard)}')
        for x in p[:40]: print('  ', x)
        tot += len(hard)
    print('전체 문제', tot)


if __name__ == '__main__':
    main()
