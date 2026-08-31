from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    package_share = FindPackageShare("buddy_robot")
    description_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution(
                [package_share, "launch", "buddy_description.launch.py"]
            )
        )
    )
    odometry_node = Node(
        package="buddy_robot",
        executable="odometry_node",
        name="buddy_odometry",
        output="screen",
    )
    return LaunchDescription([description_launch, odometry_node])
