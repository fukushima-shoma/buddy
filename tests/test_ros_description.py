import ast
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).parents[1]


class RosDescriptionTest(unittest.TestCase):
    def test_urdf_defines_the_required_robot_frames(self) -> None:
        urdf = ROOT / "urdf/buddy.urdf.xacro"
        source = urdf.read_text(encoding="utf-8")

        ET.fromstring(source)
        for frame in (
            "base_footprint",
            "base_link",
            "camera_link",
            "camera_optical_frame",
            "front_distance_sensor_link",
        ):
            self.assertIn(f'name="{frame}"', source)
        self.assertIn('<xacro:wheel side="left" sign="1"/>', source)
        self.assertIn('<xacro:wheel side="right" sign="-1"/>', source)
        self.assertIn('name="${side}_wheel_link"', source)

    def test_description_launch_runs_robot_state_publisher(self) -> None:
        launch_file = ROOT / "launch/buddy_description.launch.py"
        source = launch_file.read_text(encoding="utf-8")

        ast.parse(source)
        self.assertIn('FindPackageShare("buddy_robot")', source)
        self.assertIn('package="robot_state_publisher"', source)
        self.assertIn('"robot_description": robot_description', source)

    def test_ros_package_installs_urdf_and_declares_dependencies(self) -> None:
        setup_source = (ROOT / "setup.py").read_text(encoding="utf-8")
        package_source = (ROOT / "package.xml").read_text(encoding="utf-8")

        self.assertIn('glob("urdf/*.urdf.xacro")', setup_source)
        self.assertIn("<exec_depend>robot_state_publisher</exec_depend>", package_source)
        self.assertIn("<exec_depend>xacro</exec_depend>", package_source)

    def test_distance_node_uses_the_urdf_sensor_frame(self) -> None:
        source = (ROOT / "buddy_ros/distance_node.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('"frame_id", "front_distance_sensor_link"', source)


if __name__ == "__main__":
    unittest.main()
