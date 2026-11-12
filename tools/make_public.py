"""공개 저장소용 깨끗한 사본 만들기: python tools/make_public.py <대상 폴더>

작업 저장소에는 원문 대조표·검수 기록 같은 게임 원문이 섞인 파일이 있어서 그대로 공개하지 않는다.
공개본에는 문서·도구·한국어 번역문만 넣고, 번역 파일의 메모(notes, 원문 인용 포함)는 뺀다.
대상 폴더의 .git 은 건드리지 않고 나머지를 새로 채운다.
"""
import json, os, re, shutil, subprocess, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
KEEP_TOP = ['README.md', 'CHANGELOG.md', 'LICENSE', 'docs/README_KO.txt']
GITIGNORE = """*.gba
*.sav
*.png
build/
release/
__pycache__/
"""


def tracked(prefix):
    out = subprocess.run(['git', '-C', ROOT, '-c', 'core.quotepath=false', 'ls-files', prefix],
                         capture_output=True, text=True, encoding='utf-8', check=True).stdout
    return [l for l in out.splitlines() if l]


def main(dst):
    for name in os.listdir(dst) if os.path.isdir(dst) else []:
        if name == '.git': continue
        p = os.path.join(dst, name)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    os.makedirs(dst, exist_ok=True)
    files = KEEP_TOP + tracked('docs/releases') + tracked('tools') + tracked('work/font/hangul_order.txt') \
        + tracked('work/translation/out-id') + [f for f in tracked('work/translation/out') if f.endswith('.json')]
    n = 0
    for f in files:
        s, d = os.path.join(ROOT, f), os.path.join(dst, f)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        if f.startswith('work/translation/') and f.endswith('.json'):
            j = json.load(open(s, encoding='utf-8'))
            # 가나가 든 값은 원문 그대로 둔 조각(가짜 꼬리·깨진 원문)이라 공개본에서 뺀다
            j = {'translations': {k: v for k, v in j['translations'].items()
                                  if not (isinstance(v, str) and re.search('[぀-ヿ]', v))}}
            open(d, 'w', encoding='utf-8', newline='\n').write(json.dumps(j, ensure_ascii=False, indent=1) + '\n')
        else:
            shutil.copyfile(s, d)
        n += 1
    open(os.path.join(dst, '.gitignore'), 'w', encoding='utf-8', newline='\n').write(GITIGNORE)
    print('복사', n, '파일 →', dst)


if __name__ == '__main__':
    main(sys.argv[1])
