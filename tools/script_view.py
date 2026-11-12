"""스크립트 구간 보기: python tools/script_view.py <시작hex> <끝hex> — 명령·대사·문자열 ID를 풀어 찍는다."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import script as s, gxtext as g
seen = s.trace(); d = s.d
a, b = int(sys.argv[1], 16), int(sys.argv[2], 16)
for q in sorted(p for p in seen if a <= p < b):
    op, n, t = seen[q]; ex = ''
    if op == 0x99: ex = g.decode(d, q + 1)[0]
    if op == 5:
        sid = d[q+1] | d[q+2] << 8
        try:
            x = s.sjis_string(sid); ex = 'sid%04x ' % sid + d[x:x+40].split(b'\0')[0].decode('cp932', 'replace')
        except Exception: ex = '?'
    if t is not None: ex += ' ->%x' % t
    print('%x %-3x %-24s %s' % (q, op, d[q:q+n].hex(' ')[:24], ex[:80]))
