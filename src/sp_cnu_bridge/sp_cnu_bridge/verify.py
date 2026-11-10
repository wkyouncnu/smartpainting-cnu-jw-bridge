"""종단 검증 — TCP 로 받은 X·Y·Z·RZ 가 맞는지 확인한다.

    ros2 run sp_cnu_bridge verify                       # 30 초 측정 → 표 + PNG
    ros2 run sp_cnu_bridge verify --ros-args -p duration:=60.0 -p png:=/tmp/verify.png

하는 일
    · JW 처럼 TCP :5010 에 붙어 GET_CUR_MPOS 를 rate Hz 로 묻는다
    · 동시에 두 가지를 구독하며 받은 시각과 함께 모두 기록한다
        - 브리지 입력  /zerokey/position, /zerokey/orientation   (mpos_server 가 읽는 값)
        - Gazebo 참값  /ground_truth                              (로봇의 진짜 위치)
    · 끝나면 오차를 두 가지로 계산한다
        ① 브리지 정확성 : TCP 응답 ↔ '응답 직전 match_window_ms 동안 유효했던 브리지 입력' 중 가장 가까운 것
                          → mpos_server 가 변환·전송하면서 값을 틀리게 만들지 않았는가   [합격 판정]
        ② 참값 대비     : TCP 응답 ↔ '응답 순간의 최신 Gazebo 참값'
                          → 센서(zerokey_sim 50 Hz 재샘플링)까지 포함한 최신성           [참고]
    · 통계 표를 찍고 4칸 그림(XY 궤적 / X·Y 시간 / RZ 시간 / 오차)을 저장한다

합격 기준
    일치율 ≥ 99 %  — ① 오차가 위치 ≤ 1 mm (mm 반올림 ±0.5) · 헤딩 ≤ 0.1° (소수 2자리) 인 응답 비율
    응답률 ≥ 99 %,  지연 < 100 ms (사양서 응답 시한)
"""
import bisect
import math
import socket
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from nav_msgs.msg import Odometry
from geometry_msgs.msg import PointStamped, QuaternionStamped

from sp_cnu_bridge.protocol import quat_to_yaw, wrap_deg

ZK_QOS = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=10,
                    reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE)


class Verify(Node):
    def __init__(self):
        super().__init__("bridge_verify")
        self.declare_parameter("host", "127.0.0.1")
        self.declare_parameter("port", 5010)
        self.declare_parameter("rate_hz", 100.0)
        self.declare_parameter("duration", 30.0)
        self.declare_parameter("gt_topic", "/ground_truth")
        self.declare_parameter("position_topic", "/zerokey/position")
        self.declare_parameter("orientation_topic", "/zerokey/orientation")
        self.declare_parameter("png", "/tmp/bridge_verify.png")
        self.declare_parameter("pos_tol_mm", 1.0)
        self.declare_parameter("yaw_tol_deg", 0.1)
        self.declare_parameter("match_window_ms", 100.0)
        g = lambda n: self.get_parameter(n).value
        self.host, self.port = g("host"), int(g("port"))
        self.rate, self.dur, self.png = float(g("rate_hz")), float(g("duration")), g("png")
        self.ptol, self.ytol = float(g("pos_tol_mm")), float(g("yaw_tol_deg"))
        self.win = float(g("match_window_ms")) / 1000.0
        self.lock = threading.Lock()
        self.gt = None                 # 최신 참값 (x, y, z, yaw)  [m, rad]
        self.hp, self.hq = [], []      # 브리지 입력 기록: (받은 시각, x, y, z) / (받은 시각, yaw)
        self.rows = []                 # (t, X, Y, Z, RZ, gx, gy, gz, gyaw_deg, lat_ms, t_end)
        self.sent = 0
        self.done = False
        self.create_subscription(Odometry, g("gt_topic"), self._on_gt, 10)
        self.create_subscription(PointStamped, g("position_topic"), self._on_p, ZK_QOS)
        self.create_subscription(QuaternionStamped, g("orientation_topic"), self._on_q, ZK_QOS)
        threading.Thread(target=self._client, daemon=True).start()
        self.get_logger().info(
            f"검증 시작: {self.dur:.0f} s 동안 TCP {self.host}:{self.port} 응답을 "
            f"{g('position_topic')}·{g('orientation_topic')} (브리지 입력) 와 {g('gt_topic')} (참값) 에 비교")

    # ── 구독 ───────────────────────────────────────────────────────
    def _on_gt(self, m):
        p, q = m.pose.pose.position, m.pose.pose.orientation
        with self.lock:
            self.gt = (p.x, p.y, p.z, quat_to_yaw(q.x, q.y, q.z, q.w))

    def _on_p(self, m):
        with self.lock:
            self.hp.append((time.perf_counter(), m.point.x, m.point.y, m.point.z))

    def _on_q(self, m):
        q = m.quaternion
        with self.lock:
            self.hq.append((time.perf_counter(), quat_to_yaw(q.x, q.y, q.z, q.w)))

    # ── TCP 클라이언트 (JW 흉내) ───────────────────────────────────
    def _client(self):
        while (self.gt is None or not self.hp or not self.hq) and rclpy.ok():
            time.sleep(0.1)
        try:
            s = socket.create_connection((self.host, self.port), timeout=2.0)
        except OSError as e:
            self.get_logger().error(f"TCP 접속 실패 ({e}) — mpos_server 가 떠 있는지 확인")
            self.done = True
            return
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        f = s.makefile("rb")
        t0 = time.perf_counter()
        seq = 0
        period = 1.0 / self.rate
        nxt = t0
        while time.perf_counter() - t0 < self.dur and rclpy.ok():
            seq = (seq + 1) % 65536
            with self.lock:
                gt = self.gt
            ts = time.perf_counter()
            s.sendall(f"$JW,{seq},1,GET_CUR_MPOS,0\r\n".encode())
            self.sent += 1
            line = f.readline().decode().strip()
            te = time.perf_counter()
            tok = line.split(",")
            if len(tok) == 9 and tok[3] == "GET_CUR_MPOS" and int(tok[1]) == seq:
                X, Y, Z, RZ = (float(v) for v in tok[5:9])
                self.rows.append((ts - t0, X, Y, Z, RZ, gt[0] * 1000, gt[1] * 1000, gt[2] * 1000,
                                  math.degrees(gt[3]), (te - ts) * 1000, te))
            nxt += period
            sl = nxt - time.perf_counter()
            if sl > 0:
                time.sleep(sl)
        s.close()
        self.done = True

    # ── 판정 ───────────────────────────────────────────────────────
    def _window(self, hist, ht, te):
        """응답 직전 창 동안 유효했던 기록: 창 시작 때의 최신값 + 창 안에서 새로 받은 값.
        (+5 ms: 같은 메시지를 mpos_server 와 verify 가 받는 순서 차이)"""
        lo = max(0, bisect.bisect_left(ht, te - self.win) - 1)
        hi = bisect.bisect_right(ht, te + 0.005)
        return hist[lo:hi]

    def _match(self, a, hp, tp, hq, tq):
        """응답 a 의 ① 오차 → (위치 mm, 높이 mm, 헤딩 deg) 또는 None"""
        cp = self._window(hp, tp, a[10])
        cq = self._window(hq, tq, a[10])
        if not cp or not cq:
            return None
        ep, ez = min(((math.hypot(a[1] - h[1] * 1000, a[2] - h[2] * 1000), abs(a[3] - h[3] * 1000))
                      for h in cp), key=lambda e: max(e))
        ey = min(abs(wrap_deg(a[4] - math.degrees(h[1]))) for h in cq)
        return ep, ez, ey

    def report(self):
        r = self.rows
        if not r:
            print("\n[실패] 받은 응답이 없다")
            return False
        with self.lock:
            hp, hq = list(self.hp), list(self.hq)
        tp, tq = [h[0] for h in hp], [h[0] for h in hq]
        m = [self._match(a, hp, tp, hq, tq) for a in r]
        ok = [x is not None and max(x[0], x[1]) <= self.ptol and x[2] <= self.ytol for x in m]
        match_rate = sum(ok) / len(r) * 100
        mk = [x for x in m if x is not None] or [(0.0, 0.0, 0.0)]
        mp, mz, my = [x[0] for x in mk], [x[1] for x in mk], [x[2] for x in mk]
        gap = [(tp[i] - tp[i - 1]) * 1000 for i in range(1, len(tp))] or [0.0]

        ep = [math.hypot(a[1] - a[5], a[2] - a[6]) for a in r]
        ez = [abs(a[3] - a[7]) for a in r]
        ey = [abs(wrap_deg(a[4] - a[8])) for a in r]
        lat = [a[9] for a in r]
        span = r[-1][0] - r[0][0]
        travel = sum(math.hypot(r[i][5] - r[i - 1][5], r[i][6] - r[i - 1][6]) for i in range(1, len(r)))
        yaw_rng = max(a[8] for a in r) - min(a[8] for a in r)
        ok_rate = len(r) / max(1, self.sent) * 100
        rms = lambda v: math.sqrt(sum(x * x for x in v) / len(v))
        p99 = lambda v: sorted(v)[min(len(v) - 1, int(0.99 * len(v)))]
        pass_m = match_rate >= 99.0
        pass_c = ok_rate >= 99.0 and max(lat) < 100
        L = lambda b: "합격" if b else "불합격"
        W = 72
        print("\n" + "=" * W)
        print(f" 종단 검증 결과  ({len(r)} 샘플, {span:.1f} s, 평균 {len(r) / max(span, 1e-9):.1f} Hz)")
        print("=" * W)
        print(f" 로봇 이동거리 (참값) {travel:9.1f} mm      헤딩 변화폭 {yaw_rng:7.2f}°")
        print(f" ① 브리지 정확성  TCP 응답 ↔ /zerokey 입력 (직전 {self.win * 1000:.0f} ms 동안 유효한 값)")
        print(f"    위치   RMS / 최대  {rms(mp):6.2f} / {max(mp):6.2f} mm      높이 최대 {max(mz):5.2f} mm")
        print(f"    헤딩   RMS / 최대  {rms(my):6.3f} / {max(my):6.3f} °")
        print(f"    일치율 {match_rate:6.2f} %  (위치 ≤ {self.ptol} mm, 헤딩 ≤ {self.ytol}°)          [{L(pass_m)}]")
        print(f"    (/zerokey 입력 간격 평균 {sum(gap) / len(gap):5.1f} ms / 최대 {max(gap):6.1f} ms)")
        print(f" ② 참값 대비 (참고)  TCP 응답 ↔ 응답 순간의 최신 /ground_truth")
        print(f"    수평 위치  RMS / 99% / 최대  {rms(ep):6.2f} / {p99(ep):6.2f} / {max(ep):6.2f} mm")
        print(f"    높이 Z     RMS / 99% / 최대  {rms(ez):6.2f} / {p99(ez):6.2f} / {max(ez):6.2f} mm")
        print(f"    헤딩 RZ    RMS / 99% / 최대  {rms(ey):6.3f} / {p99(ey):6.3f} / {max(ey):6.3f} °")
        print(f" ③ 통신  응답률 {ok_rate:6.2f} %   지연 평균 {sum(lat) / len(lat):.2f} ms / 최대 {max(lat):.2f} ms   [{L(pass_c)}]")
        print("=" * W)
        print(" 최종: " + ("✔ 전부 합격" if (pass_m and pass_c) else "✘ 불합격 항목 있음"))
        nan = float("nan")
        self._plot(r, ep, ey, [x[0] if x else nan for x in m], [x[2] if x else nan for x in m])
        return pass_m and pass_c

    def _plot(self, r, ep, ey, mp, my):
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            print(" (matplotlib 없음 — 그림 생략)")
            return
        t = [a[0] for a in r]
        fig, ax = plt.subplots(2, 2, figsize=(12, 8))
        a = ax[0, 0]
        a.plot([x[5] for x in r], [x[6] for x in r], "k-", lw=3, alpha=.35, label="Gazebo truth")
        a.plot([x[1] for x in r], [x[2] for x in r], "r--", lw=1.2, label="TCP GET_CUR_MPOS")
        a.set_xlabel("X [mm]"); a.set_ylabel("Y [mm]"); a.set_title("XY trajectory"); a.axis("equal"); a.legend(); a.grid(alpha=.3)
        a = ax[0, 1]
        a.plot(t, [x[5] for x in r], "k-", lw=3, alpha=.35, label="X truth")
        a.plot(t, [x[1] for x in r], "r--", lw=1.2, label="X TCP")
        a.plot(t, [x[6] for x in r], "b-", lw=3, alpha=.25, label="Y truth")
        a.plot(t, [x[2] for x in r], "c--", lw=1.2, label="Y TCP")
        a.set_xlabel("time [s]"); a.set_ylabel("[mm]"); a.set_title("X, Y vs time"); a.legend(); a.grid(alpha=.3)
        a = ax[1, 0]
        a.plot(t, [x[8] for x in r], "k-", lw=3, alpha=.35, label="yaw truth")
        a.plot(t, [x[4] for x in r], "r--", lw=1.2, label="RZ TCP")
        a.set_xlabel("time [s]"); a.set_ylabel("[deg]"); a.set_title("Heading RZ vs time"); a.legend(); a.grid(alpha=.3)
        a = ax[1, 1]
        a.plot(t, ep, "-", color="#f4a6a6", lw=1, label="pos vs truth (ref) [mm]")
        a.plot(t, mp, "r-", lw=1.4, label="pos vs bridge input [mm]")
        a2 = a.twinx()
        a2.plot(t, ey, "-", color="#a6b8f4", lw=1, label="heading vs truth (ref) [deg]")
        a2.plot(t, my, "b-", lw=1.4, label="heading vs bridge input [deg]")
        a.set_xlabel("time [s]"); a.set_ylabel("[mm]", color="r"); a2.set_ylabel("[deg]", color="b")
        a.set_title("Error: vs bridge input (pass/fail) / vs truth (ref)"); a.grid(alpha=.3)
        h1, l1 = a.get_legend_handles_labels(); h2, l2 = a2.get_legend_handles_labels()
        a.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=8)
        fig.suptitle("CNU -> JW bridge end-to-end check (GET_CUR_MPOS vs /zerokey input and Gazebo truth)")
        fig.tight_layout()
        fig.savefig(self.png, dpi=110)
        print(f" 그림 저장: {self.png}")


def main():
    rclpy.init()
    n = Verify()
    try:
        while rclpy.ok() and not n.done:
            rclpy.spin_once(n, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    ok = n.report()
    n.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
