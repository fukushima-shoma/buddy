import unittest

from robot.color_detection import ColorDetection
from robot.color_follow_cli import (
    action_for_detection,
    apply_tracking_action,
    build_parser,
)
from robot.motor import BuddyDrive, MockMotorDriver


def detection(position: str) -> ColorDetection:
    return ColorDetection(
        color="red",
        area=2000.0,
        center_x=320,
        center_y=240,
        x=270,
        y=190,
        width=100,
        height=100,
        position=position,
    )


class ColorFollowCliTest(unittest.TestCase):
    def test_detection_position_selects_safe_action(self) -> None:
        self.assertEqual(action_for_detection(None), "stop")
        self.assertEqual(action_for_detection(detection("left")), "left")
        self.assertEqual(action_for_detection(detection("center")), "forward")
        self.assertEqual(action_for_detection(detection("right")), "right")

    def test_actions_control_drive_and_missing_target_stops(self) -> None:
        driver = MockMotorDriver()
        drive = BuddyDrive(driver, max_speed=1.0)

        apply_tracking_action(drive, "forward", 1.0, 1.0)
        self.assertEqual((driver.left_speed, driver.right_speed), (1.0, 1.0))

        apply_tracking_action(drive, "left", 1.0, 0.8)
        self.assertEqual((driver.left_speed, driver.right_speed), (-0.8, 0.8))

        apply_tracking_action(drive, "stop", 1.0, 1.0)
        self.assertEqual((driver.left_speed, driver.right_speed), (0.0, 0.0))

    def test_cli_defaults_to_mock_and_short_run(self) -> None:
        args = build_parser().parse_args([])

        self.assertEqual(args.backend, "mock")
        self.assertEqual(args.duration, 15.0)
        self.assertEqual(args.speed, 1.0)
        self.assertEqual(args.left_scale, 0.95)


if __name__ == "__main__":
    unittest.main()
