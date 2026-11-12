"""배포 파일 만들기: python tools/make_release.py v1.0f

- 원본 롬 → 한글판 롬(build/ 의 빌드 결과) BPS 패치를 만들고, 직접 다시 적용해 결과가 같은지 확인한다.
- release/<버전>/ 에 ARJJ_KPatch_<버전>.bps, README_KO.txt(docs/README_KO.txt 에 해시를 채움),
  3DS open_agb_firm 용 ini, SHA256SUMS.txt, 그리고 이것들을 묶은 ARJJ_KPatch_<버전>.zip 을 만든다.
"""
import hashlib, os, struct, sys, zipfile, zlib

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = os.path.join(ROOT, 'Custom Robo GX (Japan).gba')
CODE = 'ARJJ'


def crc(b): return zlib.crc32(b) & 0xFFFFFFFF


def vlq(n):
    out = bytearray()
    while True:
        x = n & 0x7F; n >>= 7
        if n == 0:
            out.append(0x80 | x); return bytes(out)
        out.append(x); n -= 1


def bps_encode(src, dst):
    """선형 BPS: 같은 자리 원본과 같으면 SourceRead, 다르면 TargetRead."""
    out = bytearray(b'BPS1') + vlq(len(src)) + vlq(len(dst)) + vlq(0)
    i, n = 0, len(dst)
    while i < n:
        same = i < len(src) and src[i] == dst[i]
        j = i
        if same:
            while j < n and j < len(src) and src[j] == dst[j]: j += 1
            # 짧은 같은 구간(4바이트 미만)은 앞뒤 TargetRead 에 붙이는 게 작다
            if j - i < 4 and j < n:
                k = j
                while k < n and not (k + 4 <= min(n, len(src)) and src[k:k+4] == dst[k:k+4]): k += 1
                out += vlq(((k - i - 1) << 2) | 1) + dst[i:k]; i = k; continue
            out += vlq(((j - i - 1) << 2) | 0)
        else:
            while j < n and not (j + 4 <= min(n, len(src)) and src[j:j+4] == dst[j:j+4]): j += 1
            out += vlq(((j - i - 1) << 2) | 1) + dst[i:j]
        i = j
    out += struct.pack('<II', crc(src), crc(dst))
    out += struct.pack('<I', crc(bytes(out)))
    return bytes(out)


def bps_apply(src, patch):
    assert patch[:4] == b'BPS1'
    p = 4
    def rd():
        nonlocal p
        data, shift = 0, 1
        while True:
            x = patch[p]; p += 1
            data += (x & 0x7F) * shift
            if x & 0x80: return data
            shift <<= 7; data += shift
    ssz, tsz, msz = rd(), rd(), rd(); p += msz
    assert ssz == len(src) and crc(src) == struct.unpack_from('<I', patch, len(patch) - 12)[0]
    out = bytearray(); end = len(patch) - 12; srel = trel = 0
    while p < end:
        d = rd(); cmd, ln = d & 3, (d >> 2) + 1
        if cmd == 0: out += src[len(out):len(out) + ln]
        elif cmd == 1: out += patch[p:p + ln]; p += ln
        elif cmd == 2:
            o = rd(); srel += (-1 if o & 1 else 1) * (o >> 1); out += src[srel:srel + ln]; srel += ln
        else:
            o = rd(); trel += (-1 if o & 1 else 1) * (o >> 1)
            for _ in range(ln): out.append(out[trel]); trel += 1
    assert len(out) == tsz
    assert crc(bytes(out)) == struct.unpack_from('<I', patch, len(patch) - 8)[0]
    assert crc(patch[:-4]) == struct.unpack_from('<I', patch, len(patch) - 4)[0]
    return bytes(out)


def hashes(b):
    return {'size': '{:,}'.format(len(b)), 'crc': '%08X' % crc(b),
            'md5': hashlib.md5(b).hexdigest(), 'sha': hashlib.sha256(b).hexdigest()}


def main(ver):
    src = open(SRC, 'rb').read()
    dst = open(os.path.join(ROOT, 'build', 'Custom Robo GX (Japan) [KO %s].gba' % ver), 'rb').read()
    out = os.path.join(ROOT, 'release', ver); os.makedirs(out, exist_ok=True)
    base = '%s_KPatch_%s' % (CODE, ver)
    patch = bps_encode(src, dst)
    assert bps_apply(src, patch) == dst, 'BPS 다시 적용 결과가 다름'
    open(os.path.join(out, base + '.bps'), 'wb').write(patch)
    h0, h1 = hashes(src), hashes(dst)
    t = open(os.path.join(ROOT, 'docs', 'README_KO.txt'), encoding='utf-8').read()
    for k, v in h0.items(): t = t.replace('{src_%s}' % k, v)
    for k, v in h1.items(): t = t.replace('{dst_%s}' % k, v)
    t = t.replace('{ver}', ver)
    assert '{' not in t, '안 채운 자리'
    open(os.path.join(out, 'README_KO.txt'), 'w', encoding='utf-8', newline='\r\n').write(t)
    ini = 'CustomRoboGX_KO_%s.ini' % ver
    open(os.path.join(out, ini), 'w', encoding='utf-8', newline='\n').write('[game]\nsaveType=eeprom_64k\n')
    files = [base + '.bps', 'README_KO.txt', ini]
    sums = ''.join('%s  %s\n' % (hashlib.sha256(open(os.path.join(out, f), 'rb').read()).hexdigest(), f) for f in files)
    open(os.path.join(out, 'SHA256SUMS.txt'), 'w', encoding='utf-8', newline='\n').write(sums)
    with zipfile.ZipFile(os.path.join(out, base + '.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
        for f in files + ['SHA256SUMS.txt']: z.write(os.path.join(out, f), f)
    print('패치', len(patch), '바이트, 다시 적용 일치')
    print('원본', h0); print('결과', h1)
    print('만든 파일', os.listdir(out))


if __name__ == '__main__':
    main(sys.argv[1])
