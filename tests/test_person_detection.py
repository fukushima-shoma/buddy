import unittest

from robot.person_detection import select_person_detection


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
