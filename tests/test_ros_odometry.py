import ast
from math import isclose, pi
from pathlib import Path
import unittest

from buddy_ros.odometry_control import (
    DifferentialDriveGeometry,
    EncoderOdometry,
    PlanarPose,
    integrate_wheel_distances,
    integrate_velocity,
    normalize_angle,
    yaw_quaternion,
)


ROOT = Path(__file__).parents[1]


class OdometryControlTest(unittest.TestCase):
    def test_straight_velocity_integrates_distance(self) -> None:
        pose = integrate_velocity(
            PlanarPose(),
            linear_x=0.3,
            angular_z=0.0,
            duration=2.0,
        )

        self.assertAlmostEqual(pose.x, 0.6)
        self.assertAlmostEqual(pose.y, 0.0)
        self.assertAlmostEqual(pose.yaw, 0.0)

    def test_rotation_integrates_yaw_without_translation(self) -> None:
        pose = integrate_velocity(
            PlanarPose(),
            linear_x=0.0,
            angular_z=pi / 2.0,
            duration=1.0,
        )

        self.assertAlmostEqual(pose.x, 0.0)
        self.assertAlmostEqual(pose.y, 0.0)
        self.assertAlmostEqual(pose.yaw, pi / 2.0)

    def test_arc_uses_differential_drive_geometry(self) -> None:
        pose = integrate_velocity(
            PlanarPose(),
            linear_x=1.0,
            angular_z=1.0,
            duration=pi / 2.0,
        )

        self.assertAlmostEqual(pose.x, 1.0)
        self.assertAlmostEqual(pose.y, 1.0)
        self.assertAlmostEqual(pose.yaw, pi / 2.0)

    def test_angles_are_normalized(self) -> None:
        self.assertAlmostEqual(normalize_angle(3.0 * pi), pi)

    def test_negative_duration_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duration"):
            integrate_velocity(
                PlanarPose(),
                linear_x=0.0,
                angular_z=0.0,
                duration=-0.1,
            )

    def test_yaw_quaternion_is_planar_and_normalized(self) -> None:
        quaternion = yaw_quaternion(pi / 2.0)

        self.assertEqual(quaternion[0:2], (0.0, 0.0))
        self.assertTrue(isclose(quaternion[2] ** 2 + quaternion[3] ** 2, 1.0))

    def test_encoder_ticks_integrate_straight_travel(self) -> None:
        odometry = EncoderOdometry(
            DifferentialDriveGeometry(0.07, 0.10, 20),
        )
        odometry.update(100, 100, timestamp=1.0)
        pose = odometry.update(120, 120, timestamp=2.0)

        self.assertAlmostEqual(pose.x, pi * 0.07)
        self.assertAlmostEqual(pose.y, 0.0)
        self.assertAlmostEqual(pose.yaw, 0.0)

    def test_opposite_wheel_ticks_rotate_in_place(self) -> None:
        geometry = DifferentialDriveGeometry(0.07, 0.10, 20)
        odometry = EncoderOdometry(geometry)
        odometry.update(0, 0, timestamp=1.0)
        pose = odometry.update(-5, 5, timestamp=2.0)

        self.assertAlmostEqual(pose.x, 0.0)
        self.assertAlmostEqual(pose.y, 0.0)
        self.assertGreater(pose.yaw, 0.0)

    def test_wheel_distances_support_reverse_arcs(self) -> None:
        pose = integrate_wheel_distances(
            PlanarPose(),
            left_distance=-0.2,
            right_distance=-0.1,
            wheel_separation=0.1,
        )

        self.assertLess(pose.x, 0.0)
        self.assertGreater(pose.yaw, 0.0)

    def test_encoder_rejects_non_monotonic_time_and_tick_spikes(self) -> None:
        odometry = EncoderOdometry(
            DifferentialDriveGeometry(0.07, 0.10, 20),
            max_tick_delta=100,
        )
        odometry.update(0, 0, timestamp=1.0)
        with self.assertRaisesRegex(ValueError, "timestamp"):
            odometry.update(1, 1, timestamp=1.0)
        with self.assertRaisesRegex(ValueError, "tick delta"):
            odometry.update(101, 0, timestamp=2.0)

    def test_invalid_encoder_geometry_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "dimensions"):
            DifferentialDriveGeometry(0.0, 0.1, 20)
        with self.assertRaisesRegex(ValueError, "ticks_per_revolution"):
            DifferentialDriveGeometry(0.07, 0.1, 0)

    def test_odometry_launch_includes_description_and_node(self) -> None:
        source = (ROOT / "launch/buddy_odometry.launch.py").read_text(
            encoding="utf-8"
        )

        ast.parse(source)
        self.assertIn('"buddy_description.launch.py"', source)
        self.assertIn('executable="odometry_node"', source)

    def test_ros_package_registers_odometry_node(self) -> None:
        setup_source = (ROOT / "setup.py").read_text(encoding="utf-8")
        package_source = (ROOT / "package.xml").read_text(encoding="utf-8")

        self.assertIn("odometry_node = buddy_ros.odometry_node:main", setup_source)
        self.assertIn("<exec_depend>nav_msgs</exec_depend>", package_source)
        self.assertIn("<exec_depend>tf2_ros</exec_depend>", package_source)


if __name__ == "__main__":
    unittest.main()
