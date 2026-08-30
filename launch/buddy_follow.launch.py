from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    motor_backend = LaunchConfiguration("motor_backend")
    distance_backend = LaunchConfiguration("distance_backend")
    person_backend = LaunchConfiguration("person_backend")
    power_backend = LaunchConfiguration("power_backend")
    max_speed = LaunchConfiguration("max_speed")
    mock_distance_cm = LaunchConfiguration("mock_distance_cm")
    mock_position = LaunchConfiguration("mock_position")
    mock_power_good = LaunchConfiguration("mock_power_good")

    return LaunchDescription(
        [
            DeclareLaunchArgument("motor_backend", default_value="mock"),
            DeclareLaunchArgument("distance_backend", default_value="mock"),
            DeclareLaunchArgument("person_backend", default_value="mock"),
            DeclareLaunchArgument("power_backend", default_value="mock"),
            DeclareLaunchArgument("max_speed", default_value="0.35"),
            DeclareLaunchArgument("mock_distance_cm", default_value="200.0"),
            DeclareLaunchArgument("mock_position", default_value="center"),
            DeclareLaunchArgument("mock_power_good", default_value="true"),
            Node(
                package="buddy_robot",
                executable="power_node",
                name="buddy_power",
                output="screen",
                parameters=[
                    {
                        "backend": power_backend,
                        "mock_power_good": ParameterValue(
                            mock_power_good,
                            value_type=bool,
                        ),
                    }
                ],
            ),
            Node(
                package="buddy_robot",
                executable="motor_node",
                name="buddy_motor",
                output="screen",
                parameters=[
                    {
                        "backend": motor_backend,
                        "max_speed": ParameterValue(max_speed, value_type=float),
                    }
                ],
            ),
            Node(
                package="buddy_robot",
                executable="distance_node",
                name="buddy_distance",
                output="screen",
                parameters=[
                    {
                        "backend": distance_backend,
                        "mock_distance_cm": ParameterValue(
                            mock_distance_cm,
                            value_type=float,
                        ),
                    }
                ],
            ),
            Node(
                package="buddy_robot",
                executable="person_node",
                name="buddy_person",
                output="screen",
                parameters=[
                    {
                        "backend": person_backend,
                        "mock_position": mock_position,
                    }
                ],
            ),
            Node(
                package="buddy_robot",
                executable="follow_node",
                name="buddy_follow",
                output="screen",
                parameters=[
                    {
                        "enabled": False,
                        "require_power_status": True,
                    }
                ],
            ),
        ]
    )
