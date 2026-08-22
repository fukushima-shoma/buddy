import unittest

from robot.person_cli import build_parser, detection_status
from robot.person_detection import PersonDetection


class PersonCliTest(unittest.TestCase):
    def test_detection_status_handles_missing_person(self) -> None:
        self.assertEqual(detection_status(None), "not-found")

    def test_detection_status_returns_person_position(self) -> None:
        detection = PersonDetection(
            confidence=0.8,
            center_x=320,
            center_y=240,
            x=280,
            y=120,
            width=80,
            height=240,
            position="center",
        )

        self.assertEqual(detection_status(detection), "center")

    def test_cli_defaults_are_safe_and_headless(self) -> None:
        args = build_parser().parse_args([])

        self.assertEqual(args.duration, 15.0)
        self.assertEqual(args.backend, "mediapipe")
        self.assertEqual(args.fps, 5.0)
        self.assertEqual((args.width, args.height), (640, 480))
        self.assertIsNone(args.min_confidence)


if __name__ == "__main__":
    unittest.main()
