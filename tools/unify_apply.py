"""승인된 통일 수정안(work/translation/unify-proposed.json)을 번역 결과에 반영한다.

반영 전 out 폴더를 work/translation/before-unify/ 로 한 번만 백업한다.
수정 전 문장이 지금 번역과 다르면(그새 바뀜) 멈춘다.
"""
import json, os, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
O = os.path.join(ROOT, 'work/translation/out')
BK = os.path.join(ROOT, 'work/translation/before-unify')


def main(name='unify-proposed.json'):
    prop = json.load(open(os.path.join(ROOT, 'work/translation', name), encoding='utf-8'))
    assert prop, '수정안 0개'
    if not os.path.exists(BK):
        shutil.copytree(O, BK)
    files = {}
    for x in prop:
        f = x['batch'] + '.json'
        if f not in files: files[f] = json.load(open(os.path.join(O, f), encoding='utf-8'))
        tr = files[f]['translations']
        assert tr[x['id']] == x['before'], ('번역이 수정안과 다름', x['id'])
        tr[x['id']] = x['after']
    for f, data in files.items():
        json.dump(data, open(os.path.join(O, f), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('반영', len(prop), '파일', len(files))


if __name__ == '__main__':
    import sys
    main(*sys.argv[1:2])
