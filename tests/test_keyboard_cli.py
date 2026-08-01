import unittest

from robot.keyboard_cli import command_for_key, run_keyboard_control
from robot.motor import BuddyDrive, MockMotorDriver


class KeyboardControlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.driver = MockMotorDriver()
        self.drive = BuddyDrive(
            self.driver,
            max_speed=1.0,
            left_scale=0.95,
            right_scale=1.0,
        )

    def test_command_for_key_accepts_upper_and_lower_case(self) -> None:
        self.assertEqual(command_for_key("w"), "forward")
        self.assertEqual(command_for_key("A"), "left")
        self.assertEqual(command_for_key(" "), "stop")
        self.assertIsNone(command_for_key("x"))

    def test_keyboard_commands_drive_and_stop(self) -> None:
        keys = iter(["w", "a", " ", "q"])

        run_keyboard_control(self.drive, lambda _: next(keys), 1.0, 0.5)

        self.assertIn("left=0.95", self.driver.events)
        self.assertIn("right=1.00", self.driver.events)
        self.assertEqual(self.driver.left_speed, 0.0)
        self.assertEqual(self.driver.right_speed, 0.0)

    def test_deadman_timeout_stops_motors(self) -> None:
        keys = iter(["w", None, "q"])

        run_keyboard_control(self.drive, lambda _: next(keys), 1.0, 0.5)

        self.assertIn("stop", self.driver.events)
        self.assertEqual(self.driver.left_speed, 0.0)
        self.assertEqual(self.driver.right_speed, 0.0)


if __name__ == "__main__":
    unittest.main()
