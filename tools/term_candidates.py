"""용어 후보 모으기 → work/glossary/candidates.json

출처: 화자 이름(대사 kind=name), 스크립트 문자열 묶음 0·1·4·6, 파츠 레코드(참조 안 된 SJIS), 화면용 SJIS 중 짧은 이름꼴,
대사에 자주 나오는 가타카나 낱말. 1편·V2 용어집(V2 glossary-ko.json, 1편 포함)과 맞으면 그 번역을 붙인다.
"""
import json, os, re, sys, collections
sys.path.insert(0, os.path.dirname(__file__))
import script as s

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V2_GLOSS = r'G:/KoreanTranslation/[N64] 커스텀 로보 V2/work/glossary/glossary-ko.json'
CTRL = re.compile(r'\{..\}|\$[A-Za-z]|#[A-Z0-9]')


def clean(t):
    return CTRL.sub('', t).strip('　 ')


def main():
    dlg = json.load(open(os.path.join(ROOT, 'work/translation/dialogue.json'), encoding='utf-8'))
    sj = json.load(open(os.path.join(ROOT, 'work/translation/sjis-all.json'), encoding='utf-8'))
    v2 = json.load(open(V2_GLOSS, encoding='utf-8'))
    cand = {}

    def add(jp, cat, src, n=1):
        jp = clean(jp)
        if not jp or len(jp) > 24: return
        c = cand.setdefault(jp, {'jp': jp, 'cat': cat, 'src': set(), 'count': 0})
        c['src'].add(src); c['count'] += n

    for x in dlg:
        if x['kind'] == 'name': add(x['jp'][:-4], '인물', '화자')
    GROUP_CAT = {0: '선택지·파츠 등', 1: '인물', 4: '대회', 6: '로보'}
    for it in sj['strings']:
        for gk in it['groups']:
            g = int(gk.split(':')[0])
            if g in GROUP_CAT and it['class'] == 'display' or g == 1:
                add(it['jp'], GROUP_CAT[g], '묶음%d' % g)
    for it in sj['unreferenced']:
        if 0x6A0000 <= int(it['off'], 16) < 0x6C0000: add(it['jp'], '파츠·로보', '레코드')
    # 대사 속 가타카나 낱말
    kat = collections.Counter()
    for x in dlg:
        for w in re.findall(r'[ァ-ヶー・]{3,}', CTRL.sub('', x['jp'])):
            kat[w.strip('・')] += 1
    for w, n in kat.items():
        if n >= 3: add(w, '낱말', '대사', n)
    # 대사 등장 횟수
    alltxt = '\n'.join(CTRL.sub('', x['jp']) for x in dlg)
    out = []
    for jp, c in cand.items():
        e = v2.get(jp)
        c['src'] = sorted(c['src'])
        c['in_dialogue'] = alltxt.count(jp)
        c['ko'] = e['ko'] if e else ''
        c['from'] = ('v1' if e and e.get('src') == 'v1' else 'v2') if e else ''
        out.append(c)
    out.sort(key=lambda c: (c['from'] == '', c['cat'], -c['in_dialogue']))
    os.makedirs(os.path.join(ROOT, 'work/glossary'), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, 'work/glossary/candidates.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    cats = collections.Counter((c['cat'], bool(c['ko'])) for c in out)
    print('후보', len(out), '기존 번역 있음', sum(1 for c in out if c['ko']))
    for k, v in sorted(cats.items()): print(k, v)


if __name__ == '__main__':
    main()
