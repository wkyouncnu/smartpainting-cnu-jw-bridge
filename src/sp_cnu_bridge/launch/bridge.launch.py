"""브리지 노드 두 개만 띄운다 (Gazebo 는 따로).

    ros2 launch sp_cnu_bridge bridge.launch.py                       # 시뮬: zerokey_sim + mpos_server
    ros2 launch sp_cnu_bridge bridge.launch.py use_zerokey_sim:=false  # 실기: 실제 ZeroKey 가 /zerokey/* 를 낼 때
    ros2 launch sp_cnu_bridge bridge.launch.py source_topic:=/odom_eskf  # ESKF 추정값을 보낼 때
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    cfg = os.path.join(get_package_share_directory("sp_cnu_bridge"), "config", "bridge.yaml")
    use_sim = LaunchConfiguration("use_zerokey_sim")
    return LaunchDescription([
        DeclareLaunchArgument("use_zerokey_sim", default_value="true",
                              description="true: Gazebo 참값으로 ZeroKey 토픽을 만든다 / "
                                          "false: 실제 ZeroKey 드라이버가 /zerokey/* 를 낸다"),
        DeclareLaunchArgument("source_topic", default_value="/ground_truth",
                              description="zerokey_sim 이 읽을 Odometry 토픽"),
        DeclareLaunchArgument("port", default_value="5010", description="TCP 서버 포트"),
        Node(package="sp_cnu_bridge", executable="zerokey_sim", name="zerokey_sim",
             output="screen", condition=IfCondition(use_sim),
             parameters=[cfg, {"source_topic": LaunchConfiguration("source_topic")}]),
        Node(package="sp_cnu_bridge", executable="mpos_server", name="mpos_server",
             output="screen",
             parameters=[cfg, {"port": LaunchConfiguration("port")}]),
    ])
