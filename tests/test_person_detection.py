import unittest

from robot.person_detection import (
    mediapipe_result_to_detection,
    select_person_detection,
)


class PersonDetectionTest(unittest.TestCase):
    def test_selects_highest_confidence_person(self) -> None:
        detection = select_person_detection(
            [
                (10, 20, 50, 100, 0.3),
                (400, 30, 60, 120, 0.8),
            ],
            image_width=640,
            min_confidence=0.2,
        )

        self.assertIsNotNone(detection)
        assert detection is not None
        self.assertEqual(detection.position, "right")
        self.assertEqual(detection.confidence, 0.8)

    def test_rejects_candidates_below_confidence_threshold(self) -> None:
        detection = select_person_detection(
            [(100, 20, 50, 100, 0.1)],
            image_width=640,
            min_confidence=0.2,
        )

        self.assertIsNone(detection)

    def test_converts_mediapipe_body_circle_to_detection(self) -> None:
        result = [0, 0, 0, 0, 320, 240, 320, 440, 320, 180, 320, 80, 0.9]

        detection = mediapipe_result_to_detection(result, 640, 480)

        self.assertEqual(detection.position, "center")
        self.assertEqual((detection.center_x, detection.center_y), (320, 240))
        self.assertEqual((detection.x, detection.y), (120, 40))
        self.assertEqual((detection.width, detection.height), (400, 400))
        self.assertEqual(detection.confidence, 0.9)
