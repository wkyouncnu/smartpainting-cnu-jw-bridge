"""한 번에: Gazebo(블록 월드 + 로봇) + ZeroKey 모사 + TCP 위치 서버.

    ros2 launch sp_cnu_bridge bridge_demo.launch.py
    ros2 launch sp_cnu_bridge bridge_demo.launch.py software_render:=true   # 화면이 깨질 때
    ros2 launch sp_cnu_bridge bridge_demo.launch.py gui:=false              # 창 없이 (빠름)

다른 터미널에서 JW 흉내:  ros2 run sp_cnu_bridge jw_mock_client
로봇 움직이기        :  ros2 run sp_gazebo maneuver.py -d 0.5
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    gz = os.path.join(get_package_share_directory("sp_gazebo"), "launch", "sim.launch.py")
    br = os.path.join(get_package_share_directory("sp_cnu_bridge"), "launch", "bridge.launch.py")
    a = lambda n: LaunchConfiguration(n)
    return LaunchDescription([
        DeclareLaunchArgument("world", default_value="ship_block_cad_world"),
        DeclareLaunchArgument("x", default_value="-2.68"),
        DeclareLaunchArgument("y", default_value="-0.8775"),
        DeclareLaunchArgument("z", default_value="0.53"),
        DeclareLaunchArgument("gui", default_value="true"),
        DeclareLaunchArgument("rviz", default_value="false"),
        DeclareLaunchArgument("software_render", default_value="false"),
        DeclareLaunchArgument("port", default_value="5010"),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(gz), launch_arguments={
            "world": a("world"), "x": a("x"), "y": a("y"), "z": a("z"),
            "gui": a("gui"), "rviz": a("rviz"), "software_render": a("software_render"),
        }.items()),
        # Gazebo 가 /ground_truth 를 내기 시작할 즈음 브리지를 띄운다 (먼저 떠도 동작은 한다)
        TimerAction(period=3.0, actions=[
            IncludeLaunchDescription(PythonLaunchDescriptionSource(br),
                                     launch_arguments={"port": a("port")}.items()),
        ]),
    ])
