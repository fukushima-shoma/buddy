import unittest

from robot.color_detection import ColorDetection
from robot.live_color_cli import build_parser, detection_status


class LiveColorCliTest(unittest.TestCase):
    def test_detection_status_handles_missing_detection(self) -> None:
        self.assertEqual(detection_status(None), "not-found")

    def test_detection_status_returns_detected_position(self) -> None:
        detection = ColorDetection(
            color="red",
            area=5000,
            center_x=320,
            center_y=240,
            x=200,
            y=120,
            width=240,
            height=240,
            position="center",
        )

        self.assertEqual(detection_status(detection), "center")

    def test_cli_defaults_to_short_headless_run(self) -> None:
        args = build_parser().parse_args([])

        self.assertEqual(args.color, "red")
        self.assertEqual(args.duration, 15.0)
        self.assertEqual(args.fps, 5.0)
        self.assertEqual((args.width, args.height), (640, 480))


if __name__ == "__main__":
    unittest.main()
