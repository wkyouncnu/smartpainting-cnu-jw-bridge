"""CNU 위치 서버 — /zerokey/* 를 받아 주원(JW) 통합제어기에 TCP 로 X·Y·Z·헤딩을 준다.

    /zerokey/position    (PointStamped)       ─┐
    /zerokey/orientation (QuaternionStamped)  ─┤→ mpos_server ──TCP :5010──▶ JW 통합제어기
                                               │   (TCP 서버)      ◀── 요청 $JW,..,GET_CUR_MPOS,0
                                               │                  ──▶ 응답 $CN,..,GET_CUR_MPOS,4,X,Y,Z,RZ
                                               └→ /cnu_bridge/mpos (디버그용 재발행)

사양서상 **CN(충남대)이 서버, JW(주원)가 클라이언트**다. 우리가 먼저 보내지 않는다.
JW 가 100 Hz 로 GET_CUR_MPOS 를 물으면 그때마다 최신 값으로 답한다.

단위 (기본값, 파라미터로 바꿀 수 있다)
    X, Y, Z : mm, 정수            (pos_scale=1000, pos_decimals=0)
    RZ      : deg, 소수 2자리, [-180, 180), ENU(+X 기준 반시계 +)

이 저장소의 목표는 GET_CUR_MPOS 다. 다만 사양서 시퀀스(2-5)상 JW 는
GET_VERSION → GET_LOCALIZATION_STATUS(=2 확인) → REQ_ORIGIN_INIT(=1 확인) 를 거쳐야
GET_CUR_MPOS 로 넘어가므로, 이 셋과 SET_* 계열은 최소 응답만 한다 (아래 표).

    명령                      응답
    GET_VERSION               1, 100
    GET_LOCALIZATION_STATUS   2, <상태>, 0   상태: 0 데이터 없음 / 1 끊김(stale) / 2 정상
    REQ_ORIGIN_INIT           2, 1, 0       (오프셋 반영은 구현 안 함 — 항상 완료)
    GET_CUR_MPOS              4, X, Y, Z, RZ
    GET_CUR_MDELTA            4, dX, dY, dZ, dRZ   직전 GET_CUR_MDELTA 이후 변화량
    SET_ORG_POS_OFFS / SET_CUR_APOS / SET_CUR_AVEL / SET_ROLLER_ENC   0 (수신 확인만)

    ros2 run sp_cnu_bridge mpos_server
    ros2 run sp_cnu_bridge mpos_server --ros-args -p port:=5010 -p yaw_decimals:=1
"""
import math
import socket
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from geometry_msgs.msg import PointStamped, QuaternionStamped, PoseStamped
from std_msgs.msg import String, Float64

from sp_cnu_bridge.protocol import (Block, FrameError, build_frame, parse_frame,
                                    quat_to_yaw, mpos_fields, fmt_num, wrap_deg,
                                    split_lines)

ZK_QOS = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=10,
                    reliability=ReliabilityPolicy.RELIABLE,
                    durability=DurabilityPolicy.VOLATILE)

PROTOCOL_VERSION = "100"   # 1.00


class MposServer(Node):
    def __init__(self):
        super().__init__("mpos_server")
        self.declare_parameter("host", "0.0.0.0")
        self.declare_parameter("port", 5010)
        self.declare_parameter("position_topic", "/zerokey/position")
        self.declare_parameter("orientation_topic", "/zerokey/orientation")
        self.declare_parameter("pos_scale", 1000.0)     # m → mm
        self.declare_parameter("pos_decimals", 0)
        self.declare_parameter("yaw_decimals", 2)
        self.declare_parameter("stale_timeout_s", 0.3)  # 사양서 2-7: 300 ms 넘으면 무효
        self.declare_parameter("log_every_n", 100)      # 요청 N 번마다 한 줄 로그 (100 Hz → 1 s)
        g = lambda n: self.get_parameter(n).value
        self.host, self.port = g("host"), int(g("port"))
        self.pos_scale = float(g("pos_scale"))
        self.pos_dec, self.yaw_dec = int(g("pos_decimals")), int(g("yaw_decimals"))
        self.stale = float(g("stale_timeout_s"))
        self.log_n = max(1, int(g("log_every_n")))

        self.lock = threading.Lock()
        self.pos = None      # (x, y, z) [m]
        self.yaw = None      # [rad]
        self.t_pos = 0.0
        self.t_yaw = 0.0
        self.delta_ref = None  # GET_CUR_MDELTA 기준점
        self.n_req = 0
        self.n_clients = 0

        self.create_subscription(PointStamped, g("position_topic"), self._on_pos, ZK_QOS)
        self.create_subscription(QuaternionStamped, g("orientation_topic"), self._on_ori, ZK_QOS)
        self.pub_pose = self.create_publisher(PoseStamped, "/cnu_bridge/mpos", 10)
        self.pub_head = self.create_publisher(Float64, "/cnu_bridge/heading_deg", 10)
        self.pub_tx = self.create_publisher(String, "/cnu_bridge/last_tx", 10)
        self.create_timer(0.1, self._republish)     # 디버그 토픽 10 Hz

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind((self.host, self.port))
        except OSError as e:
            self.get_logger().fatal(
                f"포트 {self.port} 를 열 수 없다 ({e}). 이미 서버가 떠 있는지 확인: "
                f"ss -ltnp | grep {self.port}")
            raise
        self.sock.listen(4)
        threading.Thread(target=self._accept_loop, daemon=True).start()
        self.get_logger().info(
            f"TCP 서버 대기 {self.host}:{self.port}  (단위 X·Y·Z ×{self.pos_scale:g}, "
            f"소수 {self.pos_dec}자리 / RZ deg 소수 {self.yaw_dec}자리)")

    # ------------------------------------------------------------ ROS 입력
    def _on_pos(self, m: PointStamped):
        with self.lock:
            self.pos = (m.point.x, m.point.y, m.point.z)
            self.t_pos = time.monotonic()

    def _on_ori(self, m: QuaternionStamped):
        q = m.quaternion
        with self.lock:
            self.yaw = quat_to_yaw(q.x, q.y, q.z, q.w)
            self.t_yaw = time.monotonic()

    def _snapshot(self):
        with self.lock:
            return self.pos, self.yaw, min(self.t_pos, self.t_yaw)

    def _status(self):
        pos, yaw, t = self._snapshot()
        if pos is None or yaw is None:
            return 0
        return 2 if time.monotonic() - t <= self.stale else 1

    def _republish(self):
        pos, yaw, _ = self._snapshot()
        if pos is None or yaw is None:
            return
        ps = PoseStamped()
        ps.header.stamp = self.get_clock().now().to_msg()
        ps.header.frame_id = "zerokey"
        ps.pose.position.x, ps.pose.position.y, ps.pose.position.z = pos
        ps.pose.orientation.z = math.sin(yaw / 2)
        ps.pose.orientation.w = math.cos(yaw / 2)
        self.pub_pose.publish(ps)
        self.pub_head.publish(Float64(data=wrap_deg(math.degrees(yaw))))

    # ------------------------------------------------------------ 명령 처리
    def handle_block(self, blk: Block) -> Block:
        c = blk.cmd
        if c == "GET_CUR_MPOS":
            pos, yaw, _ = self._snapshot()
            if pos is None or yaw is None:
                pos, yaw = (0.0, 0.0, 0.0), 0.0
            return Block(c, mpos_fields(*pos, yaw, self.pos_scale, self.pos_dec, self.yaw_dec))
        if c == "GET_VERSION":
            return Block(c, [PROTOCOL_VERSION])
        if c == "GET_LOCALIZATION_STATUS":
            return Block(c, [str(self._status()), "0"])
        if c == "REQ_ORIGIN_INIT":
            return Block(c, ["1", "0"])
        if c == "GET_CUR_MDELTA":
            pos, yaw, _ = self._snapshot()
            if pos is None or yaw is None:
                return Block(c, ["0", "0", "0", "0"])
            ref = self.delta_ref or (pos, yaw)
            self.delta_ref = (pos, yaw)
            d = [(pos[i] - ref[0][i]) * self.pos_scale for i in range(3)]
            dyaw = wrap_deg(math.degrees(yaw - ref[1]))
            return Block(c, [fmt_num(v, self.pos_dec) for v in d] + [fmt_num(dyaw, self.yaw_dec)])
        if c in ("SET_ORG_POS_OFFS", "SET_CUR_APOS", "SET_CUR_AVEL", "SET_ROLLER_ENC"):
            return Block(c, [])
        return None   # 모르는 명령 — 응답 블록을 만들지 않는다

    # ------------------------------------------------------------ TCP
    def _accept_loop(self):
        while rclpy.ok():
            try:
                conn, addr = self.sock.accept()
            except OSError:
                break
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            threading.Thread(target=self._serve, args=(conn, addr), daemon=True).start()

    def _serve(self, conn, addr):
        self.n_clients += 1
        self.get_logger().info(f"JW 접속: {addr[0]}:{addr[1]} (접속 {self.n_clients})")
        buf = b""
        try:
            while rclpy.ok():
                chunk = conn.recv(4096)
                if not chunk:
                    break
                lines, buf = split_lines(buf + chunk)
                for line in lines:
                    try:
                        req = parse_frame(line)
                    except FrameError as e:
                        self.get_logger().warn(f"형식 오류 무시: {e}")
                        continue
                    out, unknown = [], []
                    for blk in req.blocks:
                        r = self.handle_block(blk)
                        (out.append(r) if r is not None else unknown.append(blk.cmd))
                    if unknown:
                        self.get_logger().warn(f"모르는 명령 건너뜀: {unknown}")
                    if not out:
                        continue
                    tx = build_frame("CN", req.seq, out)
                    conn.sendall(tx.encode("ascii"))
                    self.n_req += 1
                    if self.n_req % self.log_n == 1 or req.blocks[0].cmd != "GET_CUR_MPOS":
                        self.get_logger().info(f"RX {line}  →  TX {tx.strip()}")
                    self.pub_tx.publish(String(data=tx.strip()))
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            self.get_logger().warn(f"연결 끊김 {addr[0]}: {e}")
        finally:
            conn.close()
            self.n_clients -= 1
            self.get_logger().info(f"JW 연결 종료: {addr[0]}:{addr[1]} (남은 접속 {self.n_clients})")

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def main():
    rclpy.init()
    node = MposServer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
