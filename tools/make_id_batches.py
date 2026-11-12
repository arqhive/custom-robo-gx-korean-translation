"""대사 재번역용 ID별 묶음(같은 원문도 줄마다 따로).

work/translation/dialogue.json(제외 목록 뺀 것)을 ID(롬 주소) 순서로 CHUNK 줄씩 나눠
work/translation/idbatches/dlg-NNN.json 에 쓴다(원문이 들어 있어 커밋 제외).
번역 결과는 work/translation/out-id/dlg-NNN.json  {"translations": {id: 번역}} (커밋 대상).
사용자가 실행 검수에서 정한 줄(locked.json)은 항목에 "locked" 로 붙인다.
"""
import json, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TR = os.path.join(ROOT, 'work', 'translation')
CHUNK = 150


def main():
    ex = set(json.load(open(os.path.join(TR, 'exclude.json'), encoding='utf-8')))
    lk = json.load(open(os.path.join(TR, 'locked.json'), encoding='utf-8'))['dlg']
    dlg = [e for e in json.load(open(os.path.join(TR, 'dialogue.json'), encoding='utf-8')) if e['id'] not in ex]
    dlg.sort(key=lambda e: int(e['id'], 16))
    od = os.path.join(TR, 'idbatches'); os.makedirs(od, exist_ok=True)
    os.makedirs(os.path.join(TR, 'out-id'), exist_ok=True)
    n = 0
    for k in range(0, len(dlg), CHUNK):
        items = []
        for e in dlg[k:k + CHUNK]:
            it = {f: e[f] for f in ('id', 'label', 'speaker', 'kind', 'width', 'jp') if f in e}
            if e['jp'] in lk: it['locked'] = lk[e['jp']]
            items.append(it)
        json.dump(items, open(os.path.join(od, 'dlg-%03d.json' % n), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        n += 1
    print('대사', len(dlg), '묶음', n, '고정 줄 표시', sum(1 for e in dlg if e['jp'] in lk))


if __name__ == '__main__':
    main()
