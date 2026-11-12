"""mGBA GDB 서버(-g, 포트 2345)에 붙어 상태 저장에서 키를 넣고, 글꼴 코드 찾기(0x8004918)에 들어오는 글자를 기록한다.

python tools/gdb_probe.py <키 비트hex> <기록 개수>
  (먼저 mgba-sdl.exe -g -t <상태 파일> <롬> 을 띄워 둔다)
기록: 글자 코드(r1), 돌아갈 곳(lr), r0~r7, 스택 위 16칸.
"""
import socket, struct, sys, time

HOST, PORT = '127.0.0.1', 2345
INPUT_DONE = 0x08000C4A          # 키 입력 갱신 함수 끝(0x02000020 새로 눌림, 0x02000004 반복 포함)
LOOKUP = 0x08004918              # 글꼴 코드 2진 탐색(r0=문맥, r1=코드)


class G:
    def __init__(self):
        self.s = socket.create_connection((HOST, PORT), timeout=30)
        self.buf = b''

    def send(self, cmd):
        data = cmd.encode()
        pkt = b'$' + data + b'#' + ('%02x' % (sum(data) & 0xFF)).encode()
        self.s.sendall(pkt)
        return self.recv()

    def recv(self):
        while True:
            while b'#' not in self.buf or len(self.buf) < self.buf.index(b'#') + 3:
                self.buf += self.s.recv(65536)
            i = self.buf.find(b'$')
            if i < 0:
                self.buf = b''; continue
            j = self.buf.index(b'#', i)
            body = self.buf[i+1:j]; self.buf = self.buf[j+3:]
            self.s.sendall(b'+')
            return body.decode('latin1')

    def regs(self):
        r = self.send('g')
        return [struct.unpack('<I', bytes.fromhex(r[8*i:8*i+8]))[0] for i in range(16)]

    def mem(self, a, n):
        return bytes.fromhex(self.send('m%x,%x' % (a, n)))

    def write(self, a, data):
        return self.send('M%x,%x:%s' % (a, len(data), data.hex()))


def watch_main():
    """python tools/gdb_probe.py watch <키hex> <감시 주소hex> <길이hex> <기록 개수>: VRAM 쓰기 감시점에서 pc·lr·레지스터 기록."""
    key = int(sys.argv[2], 16); addr = int(sys.argv[3], 16); ln = int(sys.argv[4], 16); want = int(sys.argv[5])
    g = G(); g.s.sendall(b'+')
    print('연결', g.send('?'))
    print('중단점 입력', g.send('Z0,%x,2' % INPUT_DONE)); g.send('c')
    g.write(0x02000020, struct.pack('<H', key)); g.write(0x02000004, struct.pack('<H', key))
    g.send('z0,%x,2' % INPUT_DONE)
    print('감시점', g.send('Z2,%x,%x' % (addr, ln)))
    for k in range(want):
        r = g.send('c')
        rg = g.regs(); st = g.mem(rg[13], 64)
        print('정지', r, 'pc=%08X lr=%08X' % (rg[15], rg[14]), ' '.join('r%d=%08X' % (i, rg[i]) for i in range(8)))
        print('   스택', ' '.join('%08X' % v for v in struct.unpack('<16I', st)))
    g.send('z2,%x,%x' % (addr, ln)); g.send('D')


def main():
    if sys.argv[1] == 'watch': return watch_main()
    key = int(sys.argv[1], 16); want = int(sys.argv[2])
    g = G()
    g.s.sendall(b'+')
    print('연결', g.send('?'))
    print('중단점 입력', g.send('Z0,%x,2' % INPUT_DONE))
    r = g.send('c')
    g.write(0x02000020, struct.pack('<H', key)); g.write(0x02000004, struct.pack('<H', key))
    print('키 넣음', hex(key))
    g.send('z0,%x,2' % INPUT_DONE)
    print('중단점 코드 찾기', g.send('Z0,%x,2' % LOOKUP))
    out = []
    for k in range(want):
        g.send('c')
        rg = g.regs()
        st = g.mem(rg[13], 64)
        code = rg[1] & 0xFFFF
        ch = bytes([code >> 8, code & 255]).decode('cp932', 'replace') if code > 0xFF else ''
        out.append((code, ch, rg[14], rg[:8], st))
        print('%04X %s lr=%08X r0=%08X r4=%08X r5=%08X r6=%08X r7=%08X' % (code, ch, rg[14], rg[0], rg[4], rg[5], rg[6], rg[7]))
    g.send('z0,%x,2' % LOOKUP)
    g.send('D')


if __name__ == '__main__':
    main()
