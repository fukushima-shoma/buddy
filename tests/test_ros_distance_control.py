import unittest

from buddy_ros.distance_control import range_reading_from_cm
from buddy_ros.distance_node import create_sensor


class RosDistanceControlTest(unittest.TestCase):
    def test_centimetres_are_converted_to_metres(self) -> None:
        reading = range_reading_from_cm(123.4)

        self.assertIsNotNone(reading)
        assert reading is not None
        self.assertAlmostEqual(reading.range_m, 1.234)
        self.assertEqual(reading.min_range_m, 0.04)
        self.assertEqual(reading.max_range_m, 4.0)

    def test_missing_and_invalid_measurements_are_not_published(self) -> None:
        self.assertIsNone(range_reading_from_cm(None))
        self.assertIsNone(range_reading_from_cm(float("nan")))
        self.assertIsNone(range_reading_from_cm(-1.0))

    def test_invalid_range_limits_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            range_reading_from_cm(100.0, min_range_m=2.0, max_range_m=1.0)

    def test_mock_sensor_uses_configured_distance(self) -> None:
        sensor = create_sensor("mock", mock_distance_cm=42.5)

        sensor.start()
        self.assertEqual(sensor.read_distance_cm(), 42.5)
        sensor.close()

    def test_unknown_backend_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            create_sensor("unknown")


if __name__ == "__main__":
    unittest.main()
