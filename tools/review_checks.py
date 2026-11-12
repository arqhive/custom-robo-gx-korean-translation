"""7단계 기계 검사(번역 전체) → manifests/review-machine.json

검사(분류: 문제=규칙 위반이 분명, 확인=사람이 봐야 함):
- 마침표 누락: 대사 끝(」 앞)·{07}/{08} 앞이 한글 종결형인데 부호 없음(문제)
- 말줄임표·물결표 뒤 마침표(문제)
- 그녀·그들을 한 줄에 두 번 이상(문제)
- 직역투 낱말(확인): 이 내가 / ~해 버렸 / 에 대해 / 이것을·그것을·저것을 / 하고 있다
- 같은 원문인데 번역이 다름(확인): 이름·메뉴 같은 짧은 원문(12자 이하)과 화자 이름 줄
- 숫자 불일치(확인): 원문 숫자(전각 포함)가 번역에 없음
- 전각 영숫자 남음(문제)
- 띄어쓰기: 공백 두 칸, 부호 앞 공백(문제)
- 창 폭: 대사에서 폭(23/29칸)보다 긴 낱말(문제), 단어 단위로 꺾었을 때 원문보다 2줄 이상 늘어난 쪽(확인)
"""
import json, os, re, collections, sys
sys.path.insert(0, os.path.dirname(__file__))
import check_text as ct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
O = os.path.join(ROOT, 'work/translation/out')
B = os.path.join(ROOT, 'work/translation/batches')
CTRL = re.compile(r'\{..\}|\$[A-Za-z]|#[A-Z]|%[0-9]*[sd]')
END_HANGUL = re.compile(r'[가-힣]$')
EXCL = json.load(open(os.path.join(ROOT, 'work/translation/exclude.json'), encoding='utf-8'))
Z2H = str.maketrans('０１２３４５６７８９', '0123456789')
# 줄 전체가 감탄·웃음·비명뿐이면 마침표 없어도 됨
INTERJ = re.compile(r'^[「　 ]*[가-힣]{0,3}([아앗악윽흑헉하호후히헤으우오에이]){2,}[!?…～]*$')


def load():
    items = []
    for f in sorted(os.listdir(O)):
        b = {x['id']: x for x in json.load(open(os.path.join(B, f), encoding='utf-8'))}
        tr = json.load(open(os.path.join(O, f), encoding='utf-8'))['translations']
        for i, ko in tr.items():
            if i in EXCL: continue
            x = b[i]
            items.append({'id': i, 'batch': f[:-5], 'jp': x['jp'], 'ko': ko, 'kind': x.get('kind', 'raw'),
                          'speaker': x.get('speaker', ''), 'dlg': f.startswith('dlg')})
    return items


def sentence_ends(t):
    """대사에서 문장 끝이 와야 할 조각들: 」 앞, {07}/{08} 앞 마지막 조각."""
    t = re.sub(r'\{0[1-4]\}', '', t)
    out = []
    for m in re.finditer(r'([^「」{}]+?)(」|\{0[78]\})', t):
        out.append(m.group(1))
    return out


def main():
    items = load()
    res = collections.defaultdict(list)
    for x in items:
        ko, jp, i = x['ko'], x['jp'], x['id']
        core = CTRL.sub('', ko.replace('{0A}', '아무개'))
        if x['dlg'] and x['kind'] == 'line':
            for seg in sentence_ends(ko):
                s = seg.strip('　 ')
                if not s: continue
                last = s.split('　')[-1]
                if END_HANGUL.search(s) and len(s) >= 2 and not INTERJ.match(last):
                    res['마침표 누락'].append((i, ko)); break
        if re.search(r'[…～~]\.', core): res['말줄임표·물결표 뒤 마침표'].append((i, ko))
        for w in ('그녀', '그들'):
            if core.count(w) >= 2: res['그녀·그들 반복'].append((i, ko))
        for w in ('이 내가', '해 버렸', '에 대해', '이것을', '그것을', '저것을', '하고 있다'):
            if w in core: res['직역투 확인: ' + w].append((i, ko))
        if re.search(r'[Ａ-Ｚａ-ｚ０-９]', core): res['전각 영숫자 남음'].append((i, ko))
        if re.search(r'[가-힣A-Za-z0-9]  +[가-힣A-Za-z0-9]', core) or re.search(r' [.,!?]', core):
            res['띄어쓰기(두 칸·부호 앞)'].append((i, ko))
        nj = set(re.findall(r'\d+', jp.translate(Z2H)))
        nk = set(re.findall(r'\d+', ko))
        miss = nj - nk
        kanji_nums = re.search(r'[一二三四五六七八九十百千万]', jp)
        if miss and not kanji_nums and not re.fullmatch(r'0[1-9A-F]|1[0-9A-F]|2[0-3]', ''.join(miss)):
            miss2 = {n for n in miss if f'{{{int(n):02X}}}' not in ko and f'{{{n}}}' not in ko}
            if miss2: res['숫자 불일치 확인'].append((i, '빠진 숫자 %s | %s' % (sorted(miss2), ko)))
        if x['dlg'] and x['kind'] == 'line':
            width = 23
            for seg in ct.segments(ko):
                for w in seg.split(' '):
                    if len(w) > width: res['창 폭보다 긴 낱말'].append((i, w)); break
            jl = ct.lines_by_char(jp, width)
            kl = sum(len(ct.wrap_words(s, width)[0]) for s in ct.segments(ko) if s)
            if kl >= jl + 2: res['줄 수 2줄 이상 늘어남 확인'].append((i, '%d→%d | %s' % (jl, kl, ko)))
    # 같은 원문 다른 번역(짧은 원문·화자 이름)
    by = collections.defaultdict(set)
    for x in items:
        jp_core = CTRL.sub('', x['jp'].replace('{0A}', '某')).strip('　 ')
        if len(jp_core) <= 12: by[jp_core].add(CTRL.sub('', x['ko'].replace('{0A}', '아무개')).strip('　 '))
    for jp, kos in by.items():
        if len(kos) > 1 and re.search(r'[ぁ-んァ-ヶ一-龥]', jp):
            res['같은 원문 다른 번역 확인'].append((jp, ' / '.join(sorted(kos))))
    out = {k: [{'id': a, 'text': b} for a, b in v] for k, v in res.items()}
    json.dump(out, open(os.path.join(ROOT, 'manifests/review-machine.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('검사 항목', len(items))
    for k in sorted(out, key=lambda k: -len(out[k])):
        print('%-28s %5d  예: %s' % (k, len(out[k]), out[k][0]['text'][:70]))


if __name__ == '__main__':
    main()
