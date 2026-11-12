"""7단계 원문 대조 검수 수정안 합치기 → work/translation/review-proposed.json, docs/review-table.html

- review/*.json(검수 에이전트 결과)의 fixes를 모은다. _unify-fix.json은 이미 반영했으므로 뺀다.
- 지금 번역과 같은 수정안, exclude 항목, 잘못 판단한 수정안(REJECT)은 뺀다.
- 수정안 사이 기준이 갈리는 것은 DECIDE 묶음으로 따로 표시한다(사용자 결정).
- 제어 코드가 달라진 수정안은 멈춘다.
"""
import json, os, re, html, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
O = os.path.join(ROOT, 'work/translation/out')
B = os.path.join(ROOT, 'work/translation/batches')
R = os.path.join(ROOT, 'work/translation/review')
CODE = re.compile(r'\{[0-9A-Fa-f]{2}\}|\$[A-Za-z]|#[A-Z0-9]|%[0-9]*[sd]')
# 검수 판단이 틀린 수정안: ㄱ 등 한글 낱자모는 KS X 1001 안에 있음
REJECT = {'314D58': '「ㄱ」은 KS X 1001 낱자모라 쓸 수 있음(검수 판단 오류)'}
# 기준이 갈려 사용자 결정이 필요한 것: id → 결정 묶음
DECIDE_RULES = [
    ('A その１ 표기', lambda i, jp, ko, af: bool(re.search(r'その[１-９]', jp))),
    ('B 叔父さん(카트레아)', lambda i, jp, ko, af: '叔父' in jp),
    ('C 레이디 P의 オヤジ', lambda i, jp, ko, af: 'オヤジ' in jp and '아버지' in af),
    ('D ヒトミくん(가면의 남자)', lambda i, jp, ko, af: bool(re.search(r'ヒトミ(\{..\})?(くん|さん)', jp)) and '히토미' in ko and '양' in ko),
]


def main():
    jp, ko, src = {}, {}, {}
    for f in sorted(os.listdir(O)):
        for x in json.load(open(os.path.join(B, f), encoding='utf-8')): jp[x['id']] = x['jp']
        for k, v in json.load(open(os.path.join(O, f), encoding='utf-8'))['translations'].items(): ko[k] = v; src[k] = f[:-5]
    excl = json.load(open(os.path.join(ROOT, 'work/translation/exclude.json'), encoding='utf-8'))
    out, dropped = [], collections.Counter()
    for f in sorted(os.listdir(R)):
        if not f.endswith('.json') or f.startswith('_'): continue
        for x in json.load(open(os.path.join(R, f), encoding='utf-8')).get('fixes', []):
            i, af = x['id'], x['after']
            if i not in ko: dropped['id 없음'] += 1; continue
            if i in excl: dropped['exclude'] += 1; continue
            if i in REJECT: dropped['검수 판단 오류'] += 1; continue
            if af == ko[i]: dropped['이미 반영됨'] += 1; continue
            assert CODE.findall(af) == CODE.findall(ko[i]), ('제어 코드 다름', i, af)
            cat = x.get('type', '기타')
            for name, rule in DECIDE_RULES:
                if rule(i, jp[i], ko[i], af): cat = '결정 대기 ' + name; break
            out.append({'cat': cat, 'id': i, 'batch': src[i], 'jp': jp[i], 'before': ko[i], 'after': af, 'why': x.get('why', '')})
    order = lambda c: (0 if c.startswith('결정') else 1, c)
    out.sort(key=lambda x: (order(x['cat']), x['id']))
    json.dump(out, open(os.path.join(ROOT, 'work/translation/review-proposed.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    cnt = collections.Counter(x['cat'] for x in out)
    rows = ''.join('<tr><td>%s</td><td class=id>%s<br><small>%s</small></td><td>%s</td><td class=b>%s</td><td class=a>%s</td><td><small>%s</small></td></tr>' % (
        html.escape(x['cat']), x['id'], x['batch'], html.escape(x['jp']), html.escape(x['before']), html.escape(x['after']), html.escape(x['why'])) for x in out)
    tpl = open(os.path.join(ROOT, 'docs/unify-table.html'), encoding='utf-8').read()
    head = tpl[:tpl.index('<h1>')].replace('GX 통일 대조표', 'GX 검수 대조표')
    summ = ' · '.join('%s %d' % (k, v) for k, v in sorted(cnt.items(), key=lambda kv: order(kv[0])))
    page = head + '<h1>7단계 원문 대조 검수 대조표</h1><p>모두 %d건: %s. 빠진 것: %s. 아직 반영 안 함.</p><table><tr><th>분류</th><th>id</th><th>원문</th><th>지금</th><th>수정안</th><th>이유</th></tr>%s</table></body></html>' % (
        len(out), summ, dict(dropped), rows)
    open(os.path.join(ROOT, 'docs/review-table.html'), 'w', encoding='utf-8').write(page)
    print(len(out), summ); print('빠짐', dict(dropped))


if __name__ == '__main__':
    main()
