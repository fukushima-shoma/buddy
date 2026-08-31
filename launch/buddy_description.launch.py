from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


DIMENSION_DEFAULTS = {
    "chassis_length": "0.22",
    "chassis_width": "0.10",
    "chassis_height": "0.06",
    "chassis_x": "-0.03",
    "wheel_radius": "0.035",
    "wheel_width": "0.03",
    "wheel_separation": "0.10",
    "camera_x": "0.08",
    "camera_z": "0.105",
    "distance_sensor_x": "0.08",
    "distance_sensor_z": "0.015",
    "caster_x": "-0.12",
}


def generate_launch_description() -> LaunchDescription:
    xacro_file = PathJoinSubstitution(
        [FindPackageShare("buddy_robot"), "urdf", "buddy.urdf.xacro"]
    )
    xacro_arguments = []
    for name in DIMENSION_DEFAULTS:
        xacro_arguments.extend([f" {name}:=", LaunchConfiguration(name)])
    robot_description = ParameterValue(
        Command(["xacro ", xacro_file, *xacro_arguments]),
        value_type=str,
    )

    actions = [
        DeclareLaunchArgument(name, default_value=value)
        for name, value in DIMENSION_DEFAULTS.items()
    ]
    actions.append(
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            name="buddy_robot_state_publisher",
            output="screen",
            parameters=[{"robot_description": robot_description}],
        )
    )
    return LaunchDescription(actions)
