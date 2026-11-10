#!/usr/bin/env python3
"""주원(JW) 통합제어기 흉내 — CNU 위치 서버에 붙어 GET_CUR_MPOS 를 주기적으로 묻는다.

ROS 도, 이 패키지의 다른 파일도 필요 없다. **파일 하나만 복사하면 Windows 에서도 돈다.**

    # WSL / Ubuntu
    ros2 run sp_cnu_bridge jw_mock_client
    # Windows (PowerShell) — WSL 의 서버에 붙는다 (localhost 포워딩)
    python jw_mock_client.py --host 127.0.0.1

사양서 2-5 시퀀스를 그대로 밟는다:

    1. TCP 접속         (1 s 간격 재시도, 최대 120 s)
    2. GET_VERSION
    3. GET_LOCALIZATION_STATUS  — 상태 2 가 나올 때까지 1 s 마다 반복
    4. REQ_ORIGIN_INIT           — 상태 1 이 나올 때까지 반복
    5. GET_CUR_MPOS  --rate Hz 로 반복 (기본 100 Hz). 0.2 s 마다 한 줄 출력
       응답 지연 감시: 100 ms 경고 / 300 ms 값 무효 / 1000 ms 통신 두절 → 재접속

옵션
    --host 127.0.0.1  --port 5010  --rate 100
    --raw            송수신 원문을 전부 찍는다
    --count N        GET_CUR_MPOS N 번 하고 끝낸다 (0 = 무한)
    --csv out.csv    받은 값을 CSV 로 저장
"""
import argparse
import socket
import sys
import time

CRLF = "\r\n"


def frame(seq, cmd, data=()):
    return ",".join(["$JW", str(seq % 65536), "1", cmd, str(len(data))] + [str(d) for d in data]) + CRLF


def parse(line):
    """'$CN,5,1,GET_CUR_MPOS,4,1251,842,0,45' → (seq, {cmd: [data...]})"""
    t = line.strip().lstrip("$").split(",")
    seq, n, i, out = int(t[1]), int(t[2]), 3, {}
    for _ in range(n):
        cmd, f = t[i], int(t[i + 1])
        out[cmd] = t[i + 2:i + 2 + f]
        i += 2 + f
    return seq, out


class Link:
    def __init__(self, host, port, raw=False):
        self.host, self.port, self.raw = host, port, raw
        self.sock, self.buf, self.seq = None, b"", 0

    def connect(self, max_wait=120.0):
        t0 = time.time()
        while True:
            try:
                s = socket.create_connection((self.host, self.port), timeout=1.0)
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.sock, self.buf, self.seq = s, b"", 0   # 사양서 2-8: 접속 시 SEQ 0
                print(f"[접속] {self.host}:{self.port}")
                return
            except OSError as e:
                if time.time() - t0 > max_wait:
                    raise SystemExit(f"[실패] {max_wait:.0f} s 동안 접속 못 함: {e}\n"
                                     f"  → 서버(mpos_server)가 떠 있는지, 포트 {self.port} 가 맞는지 확인")
                print(f"[재시도] 접속 대기 중... ({e.__class__.__name__})", end="\r")
                time.sleep(1.0)

    def request(self, cmd, data=(), timeout=1.0):
        """요청 하나 보내고 같은 SEQ 의 응답을 기다린다. (응답, 지연[s]) 반환. 시간 초과면 (None, timeout)."""
        self.seq = (self.seq + 1) % 65536
        tx = frame(self.seq, cmd, data)
        t0 = time.perf_counter()
        self.sock.sendall(tx.encode("ascii"))
        if self.raw:
            print("  S:", tx.strip())
        self.sock.settimeout(timeout)
        while True:
            while b"\n" in self.buf:
                raw, self.buf = self.buf.split(b"\n", 1)
                line = raw.decode("ascii", "replace").strip()
                if not line:
                    continue
                if self.raw:
                    print("  R:", line)
                seq, blocks = parse(line)
                if seq == self.seq and cmd in blocks:
                    return blocks[cmd], time.perf_counter() - t0
            remain = timeout - (time.perf_counter() - t0)
            if remain <= 0:
                return None, timeout
            self.sock.settimeout(remain)
            try:
                chunk = self.sock.recv(4096)
            except socket.timeout:
                return None, timeout
            if not chunk:
                raise ConnectionError("서버가 연결을 닫음")
            self.buf += chunk


def startup(link):
    """사양서 2-6 기동 절차 1~7단계."""
    r, dt = link.request("GET_VERSION", [100], timeout=3.0)
    print(f"[GET_VERSION] CN 버전 {int(r[0]) / 100:.2f}  ({dt * 1000:.1f} ms)" if r else "[GET_VERSION] 응답 없음")
    names = {0: "센서 미연결", 1: "센서 연결 확인", 2: "자기 위치 추정 가능", 50: "에러"}
    t0 = time.time()
    while True:
        r, _ = link.request("GET_LOCALIZATION_STATUS")
        st = int(r[0]) if r else -1
        print(f"[GET_LOCALIZATION_STATUS] {st} ({names.get(st, '응답 없음')}), 에러 {r[1] if r else '-'}")
        if st == 2:
            break
        if time.time() - t0 > 60:
            print("  [경고] 60 s 넘게 상태 2 가 아님 — Gazebo / zerokey_sim 이 돌고 있는지 확인")
            t0 = time.time()
        time.sleep(1.0)
    while True:
        r, _ = link.request("REQ_ORIGIN_INIT")
        st = int(r[0]) if r else -1
        print(f"[REQ_ORIGIN_INIT] {st} ({'반영 완료' if st == 1 else '진행 중/응답 없음'})")
        if st == 1:
            break
        time.sleep(1.0)
    print("---------------- 초기 설정 끝 → 정상 운용 (GET_CUR_MPOS) ----------------")


def run(args):
    link = Link(args.host, args.port, args.raw)
    csv = open(args.csv, "w", encoding="utf-8") if args.csv else None
    if csv:
        csv.write("t_s,X,Y,Z,RZ,latency_ms\n")
    period = 1.0 / args.rate
    n_total = 0
    while True:
        link.connect()
        try:
            startup(link)
            print(f"{'시간[s]':>8} {'SEQ':>6} {'X[mm]':>8} {'Y[mm]':>8} {'Z[mm]':>7} "
                  f"{'RZ[deg]':>8} {'지연[ms]':>8} {'실측Hz':>7}")
            t_start = t_last_ok = t_print = time.perf_counter()
            n_win, next_t = 0, time.perf_counter()
            while True:
                r, dt = link.request("GET_CUR_MPOS", timeout=1.0)
                now = time.perf_counter()
                if r is None:
                    gap = now - t_last_ok
                    if gap >= 1.0:
                        print("\n[통신 두절] 1000 ms 무응답 → 재접속 (사양서 2-8)")
                        break
                    continue
                t_last_ok = now
                n_total += 1
                n_win += 1
                if dt > 0.3:
                    print(f"  [무효] 응답 {dt * 1000:.0f} ms (> 300 ms)")
                elif dt > 0.1:
                    print(f"  [경고] 응답 {dt * 1000:.0f} ms (> 100 ms)")
                if csv:
                    csv.write(f"{now - t_start:.3f},{','.join(r)},{dt * 1000:.2f}\n")
                if now - t_print >= 0.2:
                    hz = n_win / (now - t_print)
                    print(f"{now - t_start:8.2f} {link.seq:6d} {r[0]:>8} {r[1]:>8} {r[2]:>7} "
                          f"{r[3]:>8} {dt * 1000:8.2f} {hz:7.1f}")
                    t_print, n_win = now, 0
                if args.count and n_total >= args.count:
                    print(f"[끝] GET_CUR_MPOS {n_total} 회")
                    return
                next_t += period
                sl = next_t - time.perf_counter()
                if sl > 0:
                    time.sleep(sl)
                else:
                    next_t = time.perf_counter()
        except (ConnectionError, OSError) as e:
            print(f"\n[연결 끊김] {e} → 1 s 뒤 재접속")
            time.sleep(1.0)
        finally:
            try:
                link.sock.close()
            except Exception:
                pass


def main(argv=None):
    ap = argparse.ArgumentParser(description="JW 통합제어기 모의 클라이언트 (GET_CUR_MPOS)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5010)
    ap.add_argument("--rate", type=float, default=100.0, help="GET_CUR_MPOS 요청 주기 [Hz]")
    ap.add_argument("--count", type=int, default=0, help="N 번 받고 종료 (0 = 무한)")
    ap.add_argument("--raw", action="store_true", help="송수신 원문 출력")
    ap.add_argument("--csv", default="", help="수신값 CSV 저장 경로")
    # ros2 run 이 붙이는 --ros-args 이후는 무시
    argv = sys.argv[1:] if argv is None else argv
    if "--ros-args" in argv:
        argv = argv[:argv.index("--ros-args")]
    args = ap.parse_args(argv)
    try:
        run(args)
    except KeyboardInterrupt:
        print("\n[종료] Ctrl+C")


if __name__ == "__main__":
    main()
