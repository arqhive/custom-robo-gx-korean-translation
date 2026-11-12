"""롬 전체에서 시프트JIS 문장 후보를 찾는다(JIS 1·2수준 한자·가나·전각 기호·ASCII만 허용)."""
import re, sys, json, collections
ROM = sys.argv[1] if len(sys.argv) > 1 else 'Custom Robo GX (Japan).gba'
d = open(ROM, 'rb').read()
pat = re.compile(rb'(?:[\x81-\x84\x88-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]|[\x20-\x7e\x0a])+')
ok = re.compile(r'^[\u3000-\u30ff\u4e00-\u9fff\uff01-\uff9f\u2010-\u2312\u25a0-\u266f\u0391-\u03c9\u0410-\u044f①-⑳\x20-\x7e\n]+$')
out = []
for m in pat.finditer(d):
    s = m.group()
    try: t = s.decode('cp932')
    except UnicodeDecodeError: continue
    if not ok.match(t): continue
    jp = re.findall(r'[ぁ-んァ-ヶ一-龥]', t)
    if len(jp) < 2: continue
    # 무작위 바이트 걸러내기: 한자 비율이 너무 높고 가나가 없으면 버림
    kana = re.findall(r'[ぁ-んァ-ヶー]', t)
    if not kana and len(jp) < 4: continue
    out.append((m.start(), len(s), t))
json.dump([{'off': hex(o), 'len': l, 'text': t} for o, l, t in out], open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
c = collections.Counter(o >> 16 for o, _, _ in out)
for k in sorted(c): print(hex(k << 16), c[k])
print('total', len(out))
