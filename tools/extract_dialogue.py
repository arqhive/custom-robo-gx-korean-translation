"""시나리오 대사(명령 0x99 문자열) 전부 추출.

- 흐름을 따라 닿는 명령(script.trace)의 0x99 문자열 → reach=true
- 닿지 않은 구간에서 0x99 바로 뒤 문자열로 해석되는 것 → reach=false(안 쓰는 이벤트일 수 있음)
- 화자: `{05}`로 끝나는 0x99 문자열이 화자 이름. 같은 흐름에서 그 뒤 대사의 화자로 붙인다.
- 얼굴: 명령 0xA3(얼굴 표시)이면 켜짐, 0xA4(얼굴 지움)·함수 경계(23·25·4B·00)면 꺼짐. 얼굴이 있으면 창 폭 23칸, 없으면 29칸.

python -X utf8 tools/extract_dialogue.py → work/translation/dialogue.json, manifests/dialogue-extraction.json
"""
import json, os, re, sys, collections
sys.path.insert(0, os.path.dirname(__file__))
import script as s
import gxtext as g

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = s.d


def text_at(p):
    t, q, ok = g.decode(d, p, 4000)
    return t, q, ok


def main():
    seen = s.trace()
    ps = sorted(seen)
    labels = sorted(((a, n) for n, a in s.labels()), key=lambda x: x[0])
    lab_at = {a: n for a, n in labels}

    def label_of(p):
        cur = 'Start'
        for a, n in labels:
            if a <= p: cur = n
            else: break
        return cur

    # 실행 흐름(다음 명령·점프·호출 목적지)을 따라 얼굴·화자 상태를 전파한다. 상태는 가능한 값의 집합.
    succ = {}
    for p in ps:
        op, n, tgt = seen[p]
        nx = []
        if op not in s.STOP_OPS and p + n in seen: nx.append(p + n)
        if tgt is not None and tgt in seen: nx.append(tgt)
        succ[p] = nx
    name_at = {}
    for p in ps:
        if seen[p][0] == 0x99:
            t, q, ok = text_at(p + 1)
            if t.endswith('{05}'): name_at[p] = t[:-4]
    state = {}   # p -> (얼굴 집합, 화자 집합)  : 그 명령을 실행하기 전 상태
    work = []
    for a in [s.BANK] + [a for a, _ in labels]:
        state[a] = (frozenset([False]), frozenset(['']))
        work.append(a)
    while work:
        p = work.pop()
        f, sp = state[p]
        op = seen[p][0]
        if op == 0xA3: f = frozenset([True])
        elif op == 0xA4: f = frozenset([False]); sp = frozenset([''])
        if p in name_at: sp = frozenset([name_at[p]])
        for q in succ[p]:
            old = state.get(q)
            new_st = (f, sp) if old is None else (old[0] | f, old[1] | sp)
            if new_st != old:
                state[q] = new_st; work.append(q)

    out = []
    for p in ps:
        op, n, tgt = seen[p]
        if op != 0x99: continue
        t, q, ok = text_at(p + 1)
        assert ok and q == p + n, hex(p)
        f, sp = state.get(p, (frozenset([True, False]), frozenset([''])))
        is_name = t.endswith('{05}')
        face = True in f
        out.append({'id': '%06X' % (p + 1), 'label': label_of(p), 'kind': 'name' if is_name else 'line',
                    'speaker': '' if is_name else '/'.join(sorted(x for x in sp if x)), 'face': face,
                    'face_mixed': len(f) > 1, 'width': 23 if face else 29,
                    'jp': t, 'bytes': n - 1, 'reach': True})

    # 닿지 않은 구간
    gaps = []
    for a, b in zip(ps, ps[1:]):
        e = a + seen[a][1]
        if b > e: gaps.append((e, b))
    unreached = 0
    for a, b in gaps:
        p = a
        while p < b:
            if d[p] == 0x99:
                t, q, ok = text_at(p + 1)
                core = re.sub(r'\{..\}', '', t)
                if ok and q <= b and len(core) >= 2 and len(re.findall('[ぁ-んァ-ヶー、。！？「」…一-龥]', core)) / len(core) >= 0.6:
                    out.append({'id': '%06X' % (p + 1), 'label': label_of(p), 'kind': 'name' if t.endswith('{05}') else 'line',
                                'speaker': '', 'face': False, 'width': 29, 'jp': t, 'bytes': q - p - 1, 'reach': False})
                    unreached += 1
                    p = q; continue
            p += 1
    out.sort(key=lambda x: int(x['id'], 16))
    cnt = collections.Counter(x['jp'] for x in out)
    for x in out: x['dup'] = cnt[x['jp']]
    os.makedirs(os.path.join(ROOT, 'work', 'translation'), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, 'work', 'translation', 'dialogue.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    reach = [x for x in out if x['reach']]
    chars = lambda xs: sum(len(re.sub(r'\{..\}', '', x['jp'])) for x in xs)
    summary = {
        'reached_strings': len(reach), 'reached_unique': len({x['jp'] for x in reach}), 'reached_chars': chars(reach),
        'names': sum(1 for x in reach if x['kind'] == 'name'),
        'unreached_strings': unreached, 'unreached_chars': chars([x for x in out if not x['reach']]),
        'face_lines': sum(1 for x in reach if x['face'] and x['kind'] == 'line'),
        'short_lt6_bytes': sum(1 for x in out if x['bytes'] < 6),
        'labels': len(labels), 'instructions': len(seen), 'gaps': len(gaps), 'gap_bytes': sum(b - a for a, b in gaps),
    }
    json.dump(summary, open(os.path.join(ROOT, 'manifests', 'dialogue-extraction.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
