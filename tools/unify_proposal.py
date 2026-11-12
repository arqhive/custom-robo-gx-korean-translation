"""번역 통일 수정안 만들기(반영 안 함) → work/translation/unify-proposed.json, docs/unify-table.html

수정안 = 사람이 고쳐 쓴 문장(MANUAL) + 같은 말 다른 표기 치환(REPLACE).
반영은 tools/unify_apply.py(승인 뒤)가 한다.
"""
import json, os, re, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
O = os.path.join(ROOT, 'work/translation/out')
B = os.path.join(ROOT, 'work/translation/batches')

# (분류, id, 고친 번역)
MANUAL = [
    # 결정 1: 손윗사람 さん = 씨
    *[('결정1 さん→씨', i, None) for i in ['4BA742', '4BB264', '4BD40E', '4BD628', '4BD83B', '4BDE5B', '4CE380', '4E5EB8',
                                        '4E6012', '4F4C25', '50FAA5', '50FB4B', '5215B7', '523441', '5236B5', '524649', '52465E', '52477F']],
    # 결정 2: 후카시 なのだ = ~것이다(V2)
    ('결정2 후카시', '4C7C6A', '「부르지도 않았는데 튀어나와서, 짜자자잔～{08}인 것이다아.」{07}'),
    ('결정2 후카시', '4CA861', '「아무튼, 감사하는 것이다.」{07}'),
    ('결정2 후카시', '4CA8C1', '「누구, 이 몸이랑 싸울 녀석은 없느냐!{08}　{01}고고{04}인 것이다.」{07}'),
    ('결정2 후카시', '5140AE', '「후카시 님, 참상인 것이다아앗!」{07}'),
    ('결정2 후카시', '5140FD', '「딱히 이유는 없지만 나오고 싶었던 것이다아앗! 그럼 안녕인 것이다아앗!」{07}'),
    ('결정2 후카시', '52142E', '「네놈이 {0A}인가! 내 이름은 후카시 님인 것이다!」{07}'),
    ('결정2 후카시', '521450', "「'커스텀 로보 통'이라면 모르는 사람이 없는 {01}슈퍼 엑설런트 다이내믹 커맨더{04}인 것이다아아아앗!」{07}"),
    ('결정2 후카시', '521523', '「네놈, 아무래도 무면허 커맨더, 줄여서 무커짱인 것이다!」{07}'),
    ('결정2 후카시', '52154F', '「알겠느냐, 역대 그레이트 로보 컵 챔피언도 모두 이 몸이 키워 준 거나 마찬가지인 것이다!」{07}'),
    ('결정2 후카시', '52158A', '「그만큼 이 몸은 대단하신 분님인 것이다!」{07}'),
    ('결정2 후카시', '52160E', '「마모루 따위, 이 몸의 {02}로보 닦기 담당{04}이라는 밑바닥 생활 끝에 겨우 챔프 자리를 잡은 것이다.」{07}'),
    ('결정2 후카시', '52164C', "「'통'이라면 누구나 알고 있는 것이다, 가하하핫!」{07}"),
    ('결정2 후카시', '5216A0', '「자, 가는 것이다, 승부인 것이다!」{07}'),
    ('결정2 후카시', '5216BA', '「후카시 화산! 곱빼기 대분화인 것이다아앗!{08}　고고고의 즈비즈비즈바바바아아앙인 것이다아앗!!」{08}'),
    ('결정2 후카시', '521707', '「흥가앗! 분화 실패 대분개인 것이다아앗!」{07}'),
    ('결정2 후카시', '52172E', '「잠깐 휴화산, 이후 부활인 것이다!{08}　기다리고 있는 것이다아앗!」{07}'),
    ('결정2 후카시', '5217F6', '「오옷, 결승전이야말로 후카시 님에게 어울리는 화려한 무대인 것이다아앗!」{07}'),
    ('결정2 후카시', '521876', '「가자, 나의 라이벌이여! 이 몸의 정열 열풍 파이트를 받는 것이다아앗!」{08}'),
    ('결정2 후카시', '5218B8', "「'인생을 지배하는 것은 행운이요, 영지가 아니니라'{08}……옛날 엄청 대단한 사람의 대사인 것이다.」{07}"),
    ('결정2 후카시', '5218FA', '「마치 지금의 이 몸을 위해 있는 듯한 대사인 것이다.」{07}'),
    ('결정2 후카시', '521965', '「가하하하하, 분하면 실컷 울도록 하는 것이다!{08}　눈물은 분명 내일의 파워가 되는 것이다!」{07}'),
    ('결정2 후카시', '521A51', "「시대는 지금 {01}'치유'{04}를 원하고 있는 것이다.{08}이 후카시 님도 앞으로는 포근한 하트로 대전 상대를 감싸 안듯이 해서 이겨야 하는 것이다!」{07}"),
    ('결정2 후카시', '521AE6', '「좋았어어어, 이 몸의 가슴에 뛰어들어 오도록 하는 것이다아아앗!」{08}'),
    ('결정2 후카시', '521B1C', '「크으, 글썽글썽……{08}아니, 우, 울고 있는 게 아닌 것이다!」{07}'),
    ('결정2 후카시', '521B45', '「이건……{08}그래, 콧물인 것이다!{08}　콧물은 마음의 땀이지, 인 것이다아앗!」{07}'),
    ('결정2 후카시', '521C65', '「{0A}, 네가 이 배틀에서 지면 태도를 고치고 이 몸의 {02}종{04}이 되는 것이다.」{07}'),
    ('결정2 후카시', '521C9A', '「종이라는 건 부하이고, 졸개이고, 애완 멍멍이인 것이다. 알겠느냐?」'),
    ('결정2 후카시', '521CE0', '「좋아, 꽤 시원시원한 남자인 것이다!」{07}'),
    ('결정2 후카시', '521D1A', "「후후후, {01}'GX 배틀의 늑대'{04}라고 불린 이 후카시 님의 {01}진심{04}을 받아낼 수 있을까?{08}　인 것이다.」{07}"),
    ('결정2 후카시', '521D77', '「우랴아아아앗! 제왕의 배틀을 정면으로 받아내도록 하는 것이다아앗!」{08}'),
    ('결정2 후카시', '521DB6', '「아랴아아아앗!?{08}　이, 이, 이럴 리가 없었잖아, 인 것이다아앗.」{07}'),
    ('결정2 후카시', '521DEF', '「가하하하! 이걸로 너는 이 몸의 종인 것이다아앗!」{07}'),
    # 결정 3: 히코마로 원문 반말은 반말
    ('결정3 히코마로', '4C3DA8', '「자랑이 아니야!{08}　모두에게 보여 주고 있었을 뿐이야.」{07}'),
    ('결정3 히코마로', '4C3DCE', '「그랬더니, {01}코우시로{04} 씨가 나타나서 {02}『나랑 배틀해라』{04}라고 해서…{08}거절하지 못하고 배틀했어.」{07}'),
    # B1: {0A} 뒤에 원문에 없는 「녀석」
    ('B1 녀석 빼기', '4B8A53', '「이봐 이봐, {0A} 쪽은 아직 초보자라고.」{07}'),
    ('B1 녀석 빼기', '4BACCF', '「그, 그런…{08}{0A} 쪽은 {02}커스텀 로보{04}를 막 시작한 참이에요.」{07}'),
    ('B1 녀석 빼기', '4C5D10', '{02}, 비디오에서 본 {01}수수께끼의 로보{02}의 커맨더일지도』{04}라는 거지?」{07}'),
    ('B1 녀석 빼기', '4C6657', '「{0A} 쪽이 약하다는 거냐!」{07}'),
    ('B1 녀석 빼기', '4C6EAE', '「그야, {0A} 쪽은 천재니까!{08}　…그래서, 뭔데?」{07}'),
    ('B1 녀석 빼기', '4DBC86', '「핫핫핫. {0A} 쪽은 보통이랑 다르다고!」{08}'),
    ('B1 녀석 빼기', '4DCE1E', '「그래서 {01}{0A}{04}한테 흥미를 가진 거냐?{08}　{0A} 쪽을 {01}병사{04}로 만들려고……」{07}'),
    ('B1 녀석 빼기', '4DD94C', '「쳇!{08}　{0A} 쪽이 실험 {01}도구{04}냐!」{08}'),
    # B4: 칸 추정치 때문에 깎은 설명 문장 되돌림
    ('B4 깎은 문장 되돌림', '30CC28', '폭풍에 맞으면 아래로 날아간다.'),
    ('B4 깎은 문장 되돌림', '30CC58', '폭풍에 맞으면 위로 날아간다.'),
    ('B4 깎은 문장 되돌림', '30CC88', '폭풍에 맞으면 앞쪽으로 날아간다.'),
    ('B4 깎은 문장 되돌림', '30CD44', '폭풍에 맞으면 안쪽으로 날아간다.'),
]
# 같은 말 다른 표기(문자열 치환): (분류, 찾을 말, 바꿀 말)
REPLACE = [
    ('결정1 さん→씨', re.compile(r'(마모루|코우시로|지로|토라지) (형|오빠)'), r'\1 씨'),
    ('결정2 후카시', re.compile(r'란 말이다'), '것이다'),
    ('B3 표기 통일', re.compile(r'인터넷 옥션'), '인터넷 경매'),
    ('B3 표기 통일', re.compile(r'카드 키'), '카드키'),
    ('B3 표기 통일', re.compile(r'양관'), '서양식 저택'),
    ('B3 표기 통일', re.compile(r'추천 몫'), '추천 출전권'),
    ('B3 표기 통일', re.compile(r'패퇴입니다'), '탈락입니다'),
    ('B3 표기 통일', re.compile(r'패퇴가 됩니다'), '탈락이 됩니다'),
    ('B3 표기 통일', re.compile(r'패퇴하시게 되었습니다'), '탈락하시게 되었습니다'),
    ('B3 표기 통일', re.compile(r'ＯＫ'), 'OK'),
    ('B3 표기 통일', re.compile(r'ＨＰ'), 'HP'),
]
# 「マモルお兄ちゃん」(오빠)은 さん이 아니므로 치환에서 뺌
SKIP = {'52BBE8'}
FUKASHI_IDS = {i for c, i, _ in MANUAL if c.startswith('결정2')}


def main():
    jp, ko, src = {}, {}, {}
    for f in sorted(os.listdir(O)):
        for it in json.load(open(os.path.join(B, f), encoding='utf-8')): jp[it['id']] = it['jp']; src[it['id']] = f[:-5]
        ko.update(json.load(open(os.path.join(O, f), encoding='utf-8'))['translations'])
    out = []
    manual_ids = set()
    for cat, i, new in MANUAL:
        old = ko[i]
        if new is None:  # 치환 규칙으로 만듦
            new = old
            for c, pat, rep in REPLACE:
                if c == cat: new = pat.sub(rep, new)
        if new != old:
            out.append({'cat': cat, 'id': i, 'batch': src[i], 'jp': jp[i], 'before': old, 'after': new})
        manual_ids.add(i)
    for i, old in ko.items():
        if i in manual_ids or i in SKIP: continue
        new = old
        cats = []
        for c, pat, rep in REPLACE:
            if c == '결정2 후카시' and i not in FUKASHI_IDS: continue
            if c == '결정1 さん→씨' and 'さん' not in jp[i]: continue
            n2 = pat.sub(rep, new)
            if n2 != new: cats.append(c); new = n2
        if new != old:
            out.append({'cat': cats[0], 'id': i, 'batch': src[i], 'jp': jp[i], 'before': old, 'after': new})
    order = ['결정1', '결정2', '결정3', 'B1', 'B3', 'B4']
    out.sort(key=lambda x: (order.index(x['cat'][:2] if x['cat'][:2] in order else x['cat'][:3]) if False else [k for k in order if x['cat'].startswith(k)][0], x['id']))
    json.dump(out, open(os.path.join(ROOT, 'work/translation/unify-proposed.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    # HTML 대조표
    rows = []
    for x in out:
        rows.append('<tr><td>%s</td><td class=id>%s<br><small>%s</small></td><td>%s</td><td class=b>%s</td><td class=a>%s</td></tr>' % (
            html.escape(x['cat']), x['id'], x['batch'], html.escape(x['jp']), html.escape(x['before']), html.escape(x['after'])))
    from collections import Counter
    cnt = Counter(x['cat'] for x in out)
    summ = ' · '.join('%s %d' % (k, v) for k, v in cnt.items())
    page = '''<!doctype html><html lang=ko><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>GX 통일 대조표</title>
<style>:root{--bg:#fff;--fg:#1d1d1f;--mut:#666;--line:#ddd;--b:#fbeaea;--a:#e7f5ea}
@media (prefers-color-scheme:dark){:root{--bg:#18181a;--fg:#eee;--mut:#aaa;--line:#333;--b:#3a2224;--a:#1f3324}}
body{background:var(--bg);color:var(--fg);font:14px/1.5 "Malgun Gothic",sans-serif;margin:16px}table{border-collapse:collapse;width:100%%}
td,th{border:1px solid var(--line);padding:6px;vertical-align:top}th{text-align:left;position:sticky;top:0;background:var(--bg)}
.id{white-space:nowrap;font-family:monospace}.b{background:var(--b)}.a{background:var(--a)}small{color:var(--mut)}</style></head><body>
<h1>커스텀 로보 GX 번역 통일 대조표</h1><p>모두 %d건: %s. 아직 번역 파일에 반영하지 않음.</p>
<table><tr><th>분류</th><th>id</th><th>원문</th><th>수정 전</th><th>수정 후</th></tr>%s</table></body></html>''' % (len(out), summ, ''.join(rows))
    open(os.path.join(ROOT, 'docs/unify-table.html'), 'w', encoding='utf-8').write(page)
    print(len(out), summ)


if __name__ == '__main__':
    main()
