"""화자별 말투 조사 → work/glossary/tone-survey.json

화자(대사 speaker)마다 줄 수, 1인칭, 2인칭, 어미 횟수와 예문 몇 줄을 모은다.
"""
import json, os, re, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CTRL = re.compile(r'\{..\}')
FIRST = ['オレ', 'おれ', 'ボク', 'ぼく', 'ワタシ', 'わたし', 'アタシ', 'あたし', 'ワシ', 'わし', 'ワタクシ', 'わたくし', 'オイラ', 'おいら', 'ウチ', '拙者', '我']
SECOND = ['おまえ', 'オマエ', 'キミ', 'きみ', 'アンタ', 'あんた', 'あなた', 'アナタ', 'キサマ', 'きさま', 'おぬし', 'てめえ']
ENDS = {'です・ます': r'(です|ます|でした|ました|ません|でしょう)[。！？」…]',
        'だ': r'だ[。！？」…]|だよ|だぜ|だな',
        'わ・のよ(여성)': r'わよ|わね|のよ|かしら|わ[。！」]',
        'じゃ(노인)': r'じゃ[。！？」…]|じゃろ|のう',
        'ぜ・ぞ': r'ぜ[。！」]|ぞ[。！」]',
        'でしゅ': r'でしゅ|ましゅ',
        'ござる': r'ござる|ござい'}


def main():
    dlg = json.load(open(os.path.join(ROOT, 'work/translation/dialogue.json'), encoding='utf-8'))
    by = collections.defaultdict(list)
    for x in dlg:
        if x['kind'] == 'line' and x['speaker'] and '/' not in x['speaker']:
            by[x['speaker']].append(CTRL.sub('', x['jp']))
    out = []
    for sp, lines in sorted(by.items(), key=lambda kv: -len(kv[1])):
        txt = '\n'.join(lines)
        out.append({'speaker': sp, 'lines': len(lines),
                    'first': {w: txt.count(w) for w in FIRST if txt.count(w)},
                    'second': {w: txt.count(w) for w in SECOND if txt.count(w)},
                    'ends': {k: len(re.findall(p, txt)) for k, p in ENDS.items() if re.findall(p, txt)},
                    'samples': lines[:2] + lines[len(lines)//2:len(lines)//2+2]})
    json.dump(out, open(os.path.join(ROOT, 'work/glossary/tone-survey.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for o in out:
        print('%-14s %4d  1인칭%s 2인칭%s 어미%s' % (o['speaker'], o['lines'], o['first'], o['second'], o['ends']))


if __name__ == '__main__':
    main()
