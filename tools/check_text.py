"""창 넘침 검사.

입력 JSON: [{"id":..., "kind":"dialogue|wrap|label", "jp":원문, "ko":번역, "width":29}]
- 제어 코드는 {xx}(대사 01 xx) 또는 $X(평문)로 적는다. {08}·$N·$n·\n 은 줄바꿈, {07}은 쪽 넘김.
- 한 글자 = 한 칸. 제어 코드는 칸을 차지하지 않는다.

python -X utf8 tools/check_text.py <번역.json>
"""
import json, re, sys

CTRL = re.compile(r'\{[0-9A-Fa-f]{2}\}|\$[A-Za-z]')
BREAK = {'{08}', '$N', '$n', '\n'}
PAGE = {'{07}'}


def segments(t):
    """줄바꿈·쪽 넘김 사이 구간들(제어 코드 뺀 글자)."""
    out = ['']
    for tok in re.split(r'(\{[0-9A-Fa-f]{2}\}|\$[A-Za-z]|\n)', t):
        if tok in BREAK or tok.upper() in PAGE: out.append('')
        elif CTRL.fullmatch(tok or 'x'): continue
        else: out[-1] += tok
    return out


def lines_by_char(t, width):
    return sum(max(1, -(-len(s) // width)) for s in segments(t) if s) or 1


def wrap_words(seg, width):
    """단어 단위로 꺾은 줄 목록. 폭보다 긴 단어는 글자 단위로 자른다(오류로 보고)."""
    lines, cur, long_words = [], '', []
    for w in seg.split(' '):
        if len(w) > width:
            long_words.append(w)
        cand = w if not cur else cur + ' ' + w
        if len(cand) <= width:
            cur = cand
        else:
            if cur: lines.append(cur)
            while len(w) > width:
                lines.append(w[:width]); w = w[width:]
            cur = w
    if cur: lines.append(cur)
    return lines, long_words


def check(item):
    kind, jp, ko = item['kind'], item.get('jp', ''), item['ko']
    probs = []
    if kind == 'label':
        a, b = len(CTRL.sub('', jp)), len(CTRL.sub('', ko))
        if b > a: probs.append(f'칸 넘침 {b}>{a}')
        return probs
    width = item['width']
    ko_lines = 0
    for seg in segments(ko):
        if not seg: continue
        ls, longw = wrap_words(seg, width)
        ko_lines += len(ls)
        for w in longw: probs.append(f'폭보다 긴 단어: {w}')
    jp_lines = lines_by_char(jp, width) if jp else ko_lines
    if ko_lines > jp_lines: probs.append(f'줄 수 늘어남 {jp_lines}→{ko_lines}')
    return probs


def main(path):
    items = json.load(open(path, encoding='utf-8'))
    bad = 0
    for it in items:
        p = check(it)
        if p:
            bad += 1
            print(it.get('id'), '; '.join(p))
    print(f'검사 {len(items)}개, 문제 {bad}개')


if __name__ == '__main__':
    main(sys.argv[1])
