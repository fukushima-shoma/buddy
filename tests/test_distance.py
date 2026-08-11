import unittest

from robot.distance import MockDistanceSensor, obstacle_detected
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


if __name__ == "__main__":
    unittest.main()
