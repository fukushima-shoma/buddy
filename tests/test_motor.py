import unittest

from robot.motor import BuddyDrive, MockMotorDriver


class BuddyDriveTest(unittest.TestCase):
    def setUp(self) -> None:
        self.driver = MockMotorDriver()
        self.drive = BuddyDrive(self.driver, max_speed=0.35)

    def test_forward_sets_both_motors_positive(self) -> None:
        command = self.drive.forward()

        self.assertEqual(command.left, 0.35)
        self.assertEqual(command.right, 0.35)
        self.assertEqual(self.driver.left_speed, 0.35)
        self.assertEqual(self.driver.right_speed, 0.35)

    def test_back_sets_both_motors_negative(self) -> None:
        command = self.drive.back(0.2)

        self.assertEqual(command.left, -0.2)
        self.assertEqual(command.right, -0.2)

    def test_turns_spin_in_place(self) -> None:
        left = self.drive.left(0.3)
        right = self.drive.right(0.3)

        self.assertEqual(left.left, -0.3)
        self.assertEqual(left.right, 0.3)
        self.assertEqual(right.left, 0.3)
        self.assertEqual(right.right, -0.3)

    def test_speed_is_limited_by_max_speed(self) -> None:
        command = self.drive.forward(1.0)

        self.assertEqual(command.left, 0.35)
        self.assertEqual(command.right, 0.35)

    def test_stop_sets_both_motors_zero(self) -> None:
        self.drive.forward()
        command = self.drive.stop()

        self.assertEqual(command.left, 0.0)
        self.assertEqual(command.right, 0.0)
        self.assertEqual(self.driver.left_speed, 0.0)
        self.assertEqual(self.driver.right_speed, 0.0)


if __name__ == "__main__":
    unittest.main()
