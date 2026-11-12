"""번역 묶음 만들기 → work/translation/batches/dlg-NN.json, raw-NN.json

- 대사: 같은 원문은 처음 나온 id 하나로(대표 id), 장면(라벨·주소) 순서. 묶음당 약 DLG_CHARS 글자.
- 화면 문자열: 화면용 SJIS(참조+레코드) 고유 원문. 고정 칸 글은 max_cells(원문 칸 수).
"""
import json, os, re, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DLG_CHARS = 9000
RAW_ITEMS = 250
CTRL = re.compile(r'\{..\}|\$[A-Za-z]|#[A-Z]')


def cells(t):
    return len(CTRL.sub('', t))


def main():
    dlg = json.load(open(os.path.join(ROOT, 'work/translation/dialogue.json'), encoding='utf-8'))
    sj = json.load(open(os.path.join(ROOT, 'work/translation/sjis-all.json'), encoding='utf-8'))
    out_dir = os.path.join(ROOT, 'work/translation/batches'); os.makedirs(out_dir, exist_ok=True)
    seen = {}; items = []
    for x in dlg:
        if x['jp'] in seen: continue
        seen[x['jp']] = x['id']
        items.append({'id': x['id'], 'label': x['label'], 'speaker': x['speaker'], 'kind': x['kind'], 'reach': x['reach'], 'jp': x['jp']})
    batches = []; cur = []; n = 0
    for it in items:
        cur.append(it); n += cells(it['jp'])
        if n >= DLG_CHARS:
            batches.append(cur); cur = []; n = 0
    if cur: batches.append(cur)
    for i, b in enumerate(batches):
        json.dump(b, open(os.path.join(out_dir, 'dlg-%02d.json' % i), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    # 화면 문자열
    raw = {}
    for x in sj['strings']:
        if x['class'] != 'display': continue
        r = raw.setdefault(x['jp'], {'id': x['off'], 'jp': x['jp'], 'where': [], 'groups': []})
        r['where'].append(x['off']); r['groups'] += x['groups']
    for x in sj['unreferenced']:
        r = raw.setdefault(x['jp'], {'id': x['off'], 'jp': x['jp'], 'where': [], 'groups': []})
        r['where'].append(x['off']); r['record'] = True
    ritems = sorted(raw.values(), key=lambda r: r['id'])
    for r in ritems:
        r['where'] = r['where'][:5]
        if cells(r['jp']) <= 16 and '$' not in r['jp']: r['max_cells'] = cells(r['jp'])
    rb = [ritems[i:i + RAW_ITEMS] for i in range(0, len(ritems), RAW_ITEMS)]
    for i, b in enumerate(rb):
        json.dump(b, open(os.path.join(out_dir, 'raw-%02d.json' % i), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    summary = {'dialogue_unique': len(items), 'dialogue_batches': len(batches), 'dialogue_chars': sum(cells(i['jp']) for i in items),
               'raw_unique': len(ritems), 'raw_batches': len(rb), 'raw_chars': sum(cells(r['jp']) for r in ritems)}
    json.dump(summary, open(os.path.join(ROOT, 'manifests', 'batches.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(summary)


if __name__ == '__main__':
    main()
