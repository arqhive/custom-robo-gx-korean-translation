"""사용자가 실행 검수에서 직접 정한 번역 줄(재번역 때 그대로 지킬 줄)을 git 기록에서 모은다.

대상 커밋: 사용자 승인으로 번역 파일을 고친 커밋(1차 번역·기계 검수 커밋 제외).
결과: work/translation/locked.json  {"dlg": {원문: 번역}, "raw": {id: 번역}, "src": {키: 커밋}}
대사는 지금 파일이 원문 묶음(jp→ko)이라 원문 기준으로 모은다. ID별 재번역 때 그 원문을 쓰는 모든 ID에 표시만 하고,
장면별로 다르게 해야 하는지는 줄마다 본다.
"""
import json, os, re, subprocess, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TR = os.path.join(ROOT, 'work', 'translation')
COMMITS = ['9e88487', 'acbee3f', '8393f08', '602bdd0', '35e43f4']   # 사용자 승인 수정(10/30 실행 검수, 비밀번호·연습 안내, 대전설정 2, 유스케 4줄)


def git(*a):
    return subprocess.run(['git', '-C', ROOT] + list(a), capture_output=True, text=True, encoding='utf-8', check=True).stdout


def main():
    batches = {}
    for f in os.listdir(os.path.join(TR, 'batches')):
        for x in json.load(open(os.path.join(TR, 'batches', f), encoding='utf-8')):
            batches[x['id']] = x['jp']
    locked = {'dlg': {}, 'raw': {}, 'src': {}}
    for c in COMMITS:
        files = [l for l in git('show', '--name-only', '--format=', c).splitlines() if l.startswith('work/translation/out/')]
        for path in files:
            before = json.loads(git('show', '%s^:%s' % (c, path)))['translations']
            after = json.loads(git('show', '%s:%s' % (c, path)))['translations']
            for i, v in after.items():
                if before.get(i) == v: continue
                if os.path.basename(path).startswith('dlg'):
                    locked['dlg'][batches[i]] = v; locked['src']['dlg:' + i] = c
                else:
                    locked['raw'][i] = v; locked['src']['raw:' + i] = c
    json.dump(locked, open(os.path.join(TR, 'locked.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('대사', len(locked['dlg']), '평문', len(locked['raw']))


if __name__ == '__main__':
    main()
