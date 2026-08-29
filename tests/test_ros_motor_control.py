import unittest

from buddy_ros.motor_control import DifferentialDriveController, VelocityCommand
from robot.motor import BuddyDrive, MockMotorDriver


class RosMotorControlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.driver = MockMotorDriver()
        self.controller = DifferentialDriveController(
            BuddyDrive(self.driver, max_speed=0.5),
            max_linear_speed=0.3,
            max_angular_speed=1.5,
        )

    def test_forward_velocity_drives_both_wheels(self) -> None:
        command = self.controller.apply(VelocityCommand(0.3, 0.0))

        self.assertEqual(command.left, 0.5)
        self.assertEqual(command.right, 0.5)

    def test_positive_angular_velocity_matches_verified_left_turn(self) -> None:
        command = self.controller.apply(VelocityCommand(0.0, 1.5))

        self.assertEqual(command.left, 0.5)
        self.assertEqual(command.right, -0.5)

    def test_mixed_velocity_preserves_ratio_within_limit(self) -> None:
        command = self.controller.apply(VelocityCommand(0.3, 0.75))

        self.assertEqual(command.left, 0.5)
        self.assertAlmostEqual(command.right, 1.0 / 6.0)

    def test_velocity_inputs_are_clamped(self) -> None:
        command = self.controller.apply(VelocityCommand(4.0, -4.0))

        self.assertEqual(command.left, 0.0)
        self.assertEqual(command.right, 0.5)

    def test_stop_and_close_release_drive(self) -> None:
        self.controller.apply(VelocityCommand(0.3, 0.0))
        self.controller.stop()
        self.controller.close()

        self.assertEqual(self.driver.left_speed, 0.0)
        self.assertEqual(self.driver.right_speed, 0.0)
        self.assertEqual(self.driver.events[-1], "close")

    def test_invalid_physical_speed_limits_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            DifferentialDriveController(
                BuddyDrive(self.driver),
                max_linear_speed=0.0,
            )


if __name__ == "__main__":
    unittest.main()
