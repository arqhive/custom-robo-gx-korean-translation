"""평문 시프트JIS 문자열 전부 추출·분류.

1. 롬 전체의 4바이트 정렬 낱말 중 롬 주소(0x08xxxxxx)를 가리키고, 그 자리가 올바른 SJIS 문자열(00으로 끝남)인 것
   → 참조된 문자열. 참조 위치 목록과 함께 기록한다.
2. 스크립트 문자열 묶음(0x3E4268, 묶음 0~7)에 든 문자열은 묶음 번호를 붙인다.
3. tools/scan_sjis.py 방식으로 찾은 SJIS 구간 중 참조되지 않은 것은 따로(unreferenced) 남긴다.

분류(class):
- internal: 라벨 이름(0x3E42A0), 스크립트 묶음 1·2·3·7(얼굴·큰 그림·배경·스프라이트 키), ASCII 식별자
- debug: 오류·디버그 문구
- display: 나머지(화면에 나올 수 있는 글). 같은 원문은 롬 모든 곳에서 같게 번역한다(이름 비교 보존).

python -X utf8 tools/extract_sjis.py → work/translation/sjis-all.json, manifests/sjis-extraction.json
"""
import json, os, re, struct, sys, collections
sys.path.insert(0, os.path.dirname(__file__))
import script as s

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = s.d
GROUP_SIZES = {0: 1573, 1: 54, 2: 31, 3: 55, 4: 30, 5: 1, 6: 37, 7: 45}
INTERNAL_GROUPS = {1: '얼굴 키(A3)', 2: '큰 그림 키(A5)', 3: '배경 키(AE)', 7: '스프라이트 키'}
JP = re.compile(r'[ぁ-んァ-ヶ一-龥ー]')
DEBUG = re.compile(r'%[0-9]*[dsxXc]|\(\)|バグ報告|ソフトリセット|[A-Za-z_]{4,}.*(不正|あふれ|してない|使用不能|なし)|(不正|あふれた)$|^\[%s\]')
CODE_END = 0x60000
# 흔한 글자만(잡음 거르기): 가나·JIS 1수준 한자 범위·전각 기호·ASCII
COMMON = re.compile(r'[　-ヿ一-龠！-～ -~]+')


def read_str(p):
    e = d.find(b'\0', p, p + 600)
    if e < 0 or e == p: return None
    raw = d[p:e]
    try: t = raw.decode('cp932')
    except UnicodeDecodeError: return None
    if any(ord(c) < 0x20 and c != '\n' for c in t): return None
    return t


def main():
    refs = collections.defaultdict(list)
    for o in range(0, len(d) - 4, 4):
        v = struct.unpack_from('<I', d, o)[0]
        if 0x08000000 <= v < 0x08000000 + len(d):
            refs[v - 0x08000000].append(o)
    strings = {}
    for p, rs in refs.items():
        t = read_str(p)
        if t is None or not JP.search(t): continue
        strings[p] = {'off': '%06X' % p, 'jp': t, 'bytes': len(t.encode('cp932')), 'refs': ['%06X' % r for r in rs], 'groups': []}
    # 스크립트 묶음
    for gk, n in GROUP_SIZES.items():
        base = s.u32(s.STR_GROUPS + 4 * gk) - 0x08000000
        for i in range(n):
            p = s.u32(base + 4 * i) - 0x08000000
            t = read_str(p) if 0 <= p < len(d) else None
            if t is None: continue
            it = strings.setdefault(p, {'off': '%06X' % p, 'jp': t, 'bytes': len(t.encode('cp932')), 'refs': ['%06X' % (base + 4 * i)], 'groups': []})
            it['groups'].append('%d:%d' % (gk, i))
    label_names = {s.u32(s.LABEL_NAMES + 4 * i) - 0x08000000 for i in range(s.NLABEL)}
    # 분류
    for p, it in strings.items():
        t = it['jp']; gs = {int(x.split(':')[0]) for x in it['groups']}
        if p in label_names: it['class'], it['why'] = 'internal', '라벨 이름'
        elif gs and gs <= set(INTERNAL_GROUPS): it['class'], it['why'] = 'internal', INTERNAL_GROUPS[min(gs)]
        elif DEBUG.search(t): it['class'], it['why'] = 'debug', '오류·디버그 문구'
        elif re.fullmatch(r'[A-Za-z0-9_\-./ ]+', t): it['class'], it['why'] = 'internal', 'ASCII 식별자'
        else: it['class'], it['why'] = 'display', ''
        code_refs = [r for r in it['refs'] if int(r, 16) < CODE_END]
        it['code_refs'] = len(code_refs)
    # 같은 원문이 화면용으로 한 번이라도 쓰이면 원문 단위로 화면용
    by_text = collections.defaultdict(list)
    for it in strings.values(): by_text[it['jp']].append(it)
    for t, its in by_text.items():
        if any(i['class'] == 'display' for i in its):
            for i in its:
                if i['class'] == 'internal': i['shared_with_display'] = True
    # 참조 안 된 SJIS 구간
    covered = set()
    for p, it in strings.items(): covered.update(range(p, p + it['bytes']))
    pat = re.compile(rb'(?:[\x81-\x84\x88-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]|[\x20-\x7e])+')
    unref = []
    for m in pat.finditer(d):
        if m.start() in covered: continue
        try: t = m.group().decode('cp932')
        except UnicodeDecodeError: continue
        kana = re.findall(r'[ぁ-んァ-ヶー]', t)
        if len(kana) >= 2 and len(kana) >= len(t) * 0.5 and COMMON.fullmatch(t) and d[m.start() - 1] in (0, 0x20) and not (0x4B5FA0 <= m.start() < 0x5371D8):
            unref.append({'off': '%06X' % m.start(), 'jp': t})
    items = sorted(strings.values(), key=lambda x: x['off'])
    json.dump({'strings': items, 'unreferenced': unref}, open(os.path.join(ROOT, 'work', 'translation', 'sjis-all.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    cls = collections.Counter(i['class'] for i in items)
    disp = [i for i in items if i['class'] == 'display']
    summary = {'referenced': len(items), 'by_class': dict(cls), 'display_unique': len({i['jp'] for i in disp}),
               'display_chars': sum(len(t) for t in {i['jp'] for i in disp}),
               'internal_shared_with_display': sum(1 for i in items if i.get('shared_with_display')),
               'unreferenced_runs': len(unref)}
    json.dump(summary, open(os.path.join(ROOT, 'manifests', 'sjis-extraction.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
