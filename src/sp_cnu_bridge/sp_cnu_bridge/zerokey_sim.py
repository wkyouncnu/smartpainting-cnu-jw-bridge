"""ZeroKey 모사 노드 — Gazebo 참값(/ground_truth)을 ZeroKey 와 같은 토픽·타입으로 다시 낸다.

    /ground_truth (nav_msgs/Odometry, Gazebo)
          │
     zerokey_sim  ── 주기 rate_hz 로 샘플링 + (선택) 가우시안 잡음
          │
          ├─ /zerokey/position     geometry_msgs/PointStamped       [m]
          ├─ /zerokey/orientation  geometry_msgs/QuaternionStamped
          └─ /zerokey/vel          geometry_msgs/TwistStamped       [m/s] 월드 좌표

토픽 이름·타입·QoS(Reliable, Volatile, KeepLast 10)는 실기 Simulink 모델
(Tracked_UGV_ZeroKey_XsensIMU.slx)의 ROS2 Subscribe 블록과 똑같이 맞췄다.
그래서 실제 ZeroKey 를 붙이면 이 노드만 끄면 되고, 뒤의 mpos_server 는 그대로다.

    ros2 run sp_cnu_bridge zerokey_sim
    ros2 run sp_cnu_bridge zerokey_sim --ros-args -p rate_hz:=30.0 -p pos_noise_std:=0.02
"""
import math
import random

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from nav_msgs.msg import Odometry
from geometry_msgs.msg import PointStamped, QuaternionStamped, TwistStamped

ZK_QOS = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=10,
                    reliability=ReliabilityPolicy.RELIABLE,
                    durability=DurabilityPolicy.VOLATILE)


def rotate(q, v):
    """쿼터니언 q=(x,y,z,w) 로 벡터 v 를 회전 (몸체 → 월드)."""
    x, y, z, w = q
    vx, vy, vz = v
    # t = 2 * (q_vec × v)
    tx = 2 * (y * vz - z * vy)
    ty = 2 * (z * vx - x * vz)
    tz = 2 * (x * vy - y * vx)
    return (vx + w * tx + (y * tz - z * ty),
            vy + w * ty + (z * tx - x * tz),
            vz + w * tz + (x * ty - y * tx))


class ZeroKeySim(Node):
    def __init__(self):
        super().__init__("zerokey_sim")
        self.declare_parameter("source_topic", "/ground_truth")
        self.declare_parameter("rate_hz", 50.0)
        self.declare_parameter("frame_id", "zerokey")
        self.declare_parameter("pos_noise_std", 0.0)      # [m]
        self.declare_parameter("yaw_noise_std_deg", 0.0)  # [deg]
        g = lambda n: self.get_parameter(n).value
        self.src = g("source_topic")
        self.frame = g("frame_id")
        self.pos_std = float(g("pos_noise_std"))
        self.yaw_std = math.radians(float(g("yaw_noise_std_deg")))
        rate = float(g("rate_hz"))

        self.last = None
        self.sub = self.create_subscription(Odometry, self.src, self._on_odom, 10)
        self.pub_p = self.create_publisher(PointStamped, "/zerokey/position", ZK_QOS)
        self.pub_q = self.create_publisher(QuaternionStamped, "/zerokey/orientation", ZK_QOS)
        self.pub_v = self.create_publisher(TwistStamped, "/zerokey/vel", ZK_QOS)
        self.timer = self.create_timer(1.0 / rate, self._tick)
        self.n = 0
        self.create_timer(5.0, self._report)
        self.get_logger().info(
            f"ZeroKey 모사 시작: {self.src} → /zerokey/{{position,orientation,vel}} "
            f"@ {rate:.0f} Hz, 잡음 pos {self.pos_std*1000:.0f} mm / yaw {math.degrees(self.yaw_std):.1f}°")

    def _on_odom(self, msg: Odometry):
        self.last = msg

    def _tick(self):
        m = self.last
        if m is None:
            return
        stamp = self.get_clock().now().to_msg()
        p = m.pose.pose.position
        q = m.pose.pose.orientation

        ps = PointStamped()
        ps.header.stamp = stamp
        ps.header.frame_id = self.frame
        ps.point.x = p.x + random.gauss(0, self.pos_std) if self.pos_std else p.x
        ps.point.y = p.y + random.gauss(0, self.pos_std) if self.pos_std else p.y
        ps.point.z = p.z + random.gauss(0, self.pos_std) if self.pos_std else p.z

        qs = QuaternionStamped()
        qs.header = ps.header
        if self.yaw_std:
            # 월드 Z 축 둘레로 작은 회전 dq 를 곱한다: q' = dq ⊗ q
            h = random.gauss(0, self.yaw_std) / 2
            cw, sz = math.cos(h), math.sin(h)
            qs.quaternion.w = cw * q.w - sz * q.z
            qs.quaternion.x = cw * q.x - sz * q.y
            qs.quaternion.y = cw * q.y + sz * q.x
            qs.quaternion.z = cw * q.z + sz * q.w
        else:
            qs.quaternion = q

        # Odometry.twist 는 몸체 좌표 → ZeroKey 처럼 월드 좌표로 돌려서 낸다
        tv = m.twist.twist.linear
        vx, vy, vz = rotate((q.x, q.y, q.z, q.w), (tv.x, tv.y, tv.z))
        ts = TwistStamped()
        ts.header = ps.header
        ts.twist.linear.x, ts.twist.linear.y, ts.twist.linear.z = vx, vy, vz
        ts.twist.angular = m.twist.twist.angular

        self.pub_p.publish(ps)
        self.pub_q.publish(qs)
        self.pub_v.publish(ts)
        self.n += 1

    def _report(self):
        if self.last is None:
            self.get_logger().warn(f"{self.src} 가 안 들어온다 — Gazebo 가 떠 있는지 확인")
        else:
            self.get_logger().info(f"발행 {self.n} 회 (최근 5 s)")
        self.n = 0


def main():
    rclpy.init()
    node = ZeroKeySim()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
