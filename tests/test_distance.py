import unittest

from robot.distance import (
    MockDistanceSensor,
    ObstacleLatch,
    obstacle_detected,
    retain_recent_distance,
    update_distance_median,
    update_obstacle_latch,
)
from robot.distance_cli import build_parser, create_sensor


class DistanceTest(unittest.TestCase):
    def test_obstacle_detection_uses_stop_distance(self) -> None:
        self.assertTrue(obstacle_detected(20.0, 20.0))
        self.assertTrue(obstacle_detected(10.0, 20.0))
        self.assertFalse(obstacle_detected(20.1, 20.0))
        self.assertFalse(obstacle_detected(None, 20.0))

    def test_cli_defaults_are_safe(self) -> None:
        args = build_parser().parse_args([])

        self.assertEqual(args.backend, "mock")
        self.assertEqual(args.stop_distance, 20.0)
        self.assertEqual(args.duration, 15.0)
        self.assertEqual(args.distance_mode, 2)

    def test_mock_backend_does_not_require_hardware(self) -> None:
        args = build_parser().parse_args(["--mock-distance", "12.5"])
        sensor = create_sensor(args)

        self.assertIsInstance(sensor, MockDistanceSensor)
        self.assertEqual(sensor.read_distance_cm(), 12.5)

    def test_recent_distance_is_retained_between_updates(self) -> None:
        self.assertEqual(
            retain_recent_distance(None, 42.0, 10.0, now=10.2),
            (42.0, 10.0),
        )

    def test_obstacle_latch_requires_clearance_to_release(self) -> None:
        self.assertTrue(update_obstacle_latch(59.0, 60.0, 70.0, False))
        self.assertTrue(update_obstacle_latch(65.0, 60.0, 70.0, True))
        self.assertFalse(update_obstacle_latch(70.0, 60.0, 70.0, True))

    def test_distance_median_rejects_single_spike(self) -> None:
        readings = (100.0, 102.0)

        filtered, updated = update_distance_median(20.0, readings, 3)

        self.assertEqual(filtered, 100.0)
        self.assertEqual(updated, (100.0, 102.0, 20.0))

    def test_obstacle_latch_stops_immediately_on_raw_close_reading(self) -> None:
        latch = ObstacleLatch(60.0, 70.0, resume_confirm_frames=3)

        self.assertTrue(latch.update(100.0, raw_distance_cm=20.0))

    def test_obstacle_latch_requires_consecutive_clear_readings(self) -> None:
        latch = ObstacleLatch(60.0, 70.0, resume_confirm_frames=3)
        latch.update(50.0, raw_distance_cm=50.0)

        self.assertTrue(latch.update(80.0, raw_distance_cm=80.0))
        self.assertTrue(latch.update(65.0, raw_distance_cm=65.0))
        self.assertTrue(latch.update(80.0, raw_distance_cm=80.0))
        self.assertTrue(latch.update(80.0, raw_distance_cm=80.0))
        self.assertFalse(latch.update(80.0, raw_distance_cm=80.0))


if __name__ == "__main__":
    unittest.main()
