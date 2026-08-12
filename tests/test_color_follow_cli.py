import unittest

from robot.color_detection import ColorDetection
from robot.color_follow_cli import (
    action_for_detection,
    apply_tracking_action,
    build_parser,
    create_distance_sensor,
    tracking_decision,
)
from robot.distance import MockDistanceSensor
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

    def test_large_target_stops_before_position_control(self) -> None:
        close_target = detection("left")
        close_target = ColorDetection(
            **{**close_target.__dict__, "area": 30000.0}
        )

        self.assertEqual(
            tracking_decision(close_target, stop_area=30000.0),
            ("stop", "too-close"),
        )

    def test_missing_target_reports_not_found(self) -> None:
        self.assertEqual(
            tracking_decision(None, stop_area=30000.0),
            ("stop", "not-found"),
        )

    def test_distance_stop_has_priority_over_color_tracking(self) -> None:
        self.assertEqual(
            tracking_decision(
                detection("center"),
                stop_area=30000.0,
                distance_cm=15.0,
                stop_distance_cm=20.0,
                distance_required=True,
            ),
            ("stop", "obstacle"),
        )

    def test_missing_distance_stops_when_sensor_is_required(self) -> None:
        self.assertEqual(
            tracking_decision(
                detection("center"),
                stop_area=30000.0,
                distance_cm=None,
                distance_required=True,
            ),
            ("stop", "distance-not-ready"),
        )

    def test_clear_distance_allows_color_tracking(self) -> None:
        self.assertEqual(
            tracking_decision(
                detection("right"),
                stop_area=30000.0,
                distance_cm=50.0,
                stop_distance_cm=20.0,
                distance_required=True,
            ),
            ("right", "tracking"),
        )

    def test_actions_control_drive_and_missing_target_stops(self) -> None:
        driver = MockMotorDriver()
        drive = BuddyDrive(driver, max_speed=1.0)

        apply_tracking_action(drive, "forward", 1.0, 1.0)
        self.assertEqual((driver.left_speed, driver.right_speed), (1.0, 1.0))

        apply_tracking_action(drive, "left", 1.0, 0.8)
        self.assertEqual((driver.left_speed, driver.right_speed), (0.8, -0.8))

        apply_tracking_action(drive, "stop", 1.0, 1.0)
        self.assertEqual((driver.left_speed, driver.right_speed), (0.0, 0.0))

    def test_cli_defaults_to_mock_and_short_run(self) -> None:
        args = build_parser().parse_args([])

        self.assertEqual(args.backend, "mock")
        self.assertEqual(args.duration, 15.0)
        self.assertEqual(args.speed, 1.0)
        self.assertEqual(args.left_scale, 0.95)
        self.assertEqual(args.stop_area, 30000.0)
        self.assertEqual(args.distance_backend, "none")
        self.assertEqual(args.stop_distance, 20.0)

    def test_mock_distance_backend_is_available(self) -> None:
        args = build_parser().parse_args(
            ["--distance-backend", "mock", "--mock-distance", "15"]
        )

        sensor = create_distance_sensor(args)

        self.assertIsInstance(sensor, MockDistanceSensor)
        self.assertEqual(sensor.read_distance_cm(), 15.0)


if __name__ == "__main__":
    unittest.main()
