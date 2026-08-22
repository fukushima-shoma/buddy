import unittest

from robot.person_detection import (
    PersonDetection,
    PersonAreaLatch,
    PersonDetectionStabilizer,
    mediapipe_result_to_detection,
    select_person_detection,
)


class PersonDetectionTest(unittest.TestCase):
    def make_detection(self, center_x: int) -> PersonDetection:
        return PersonDetection(
            confidence=0.8,
            center_x=center_x,
            center_y=240,
            x=center_x - 50,
            y=100,
            width=100,
            height=280,
            position="center",
        )

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

    def test_stabilizer_requires_two_consecutive_detections(self) -> None:
        stabilizer = PersonDetectionStabilizer(640, confirm_frames=2)

        first, confirming = stabilizer.update(self.make_detection(320))
        second, confirmed = stabilizer.update(self.make_detection(322))

        self.assertIsNone(first)
        self.assertTrue(confirming)
        self.assertIsNotNone(second)
        self.assertFalse(confirmed)

    def test_stabilizer_tolerates_one_missed_frame(self) -> None:
        stabilizer = PersonDetectionStabilizer(
            640,
            confirm_frames=1,
            lost_frame_tolerance=1,
        )
        detected, _ = stabilizer.update(self.make_detection(320))

        retained, _ = stabilizer.update(None)
        lost, _ = stabilizer.update(None)

        self.assertEqual(retained, detected)
        self.assertIsNone(lost)

    def test_stabilizer_uses_median_horizontal_position(self) -> None:
        stabilizer = PersonDetectionStabilizer(
            640,
            confirm_frames=1,
            position_window=3,
        )
        stabilizer.update(self.make_detection(100))
        stabilizer.update(self.make_detection(540))

        stable, _ = stabilizer.update(self.make_detection(320))

        self.assertIsNotNone(stable)
        assert stable is not None
        self.assertEqual(stable.center_x, 320)
        self.assertEqual(stable.position, "center")

    def test_person_area_latch_ignores_one_large_box(self) -> None:
        latch = PersonAreaLatch(
            stop_area=180000.0,
            resume_area=140000.0,
            window_size=3,
            stop_confirm_frames=2,
        )

        latched, _ = latch.update(self.make_detection(320))
        large = PersonDetection(
            **{**self.make_detection(320).__dict__, "width": 500, "height": 400}
        )
        latched_after_spike, filtered = latch.update(large)

        self.assertFalse(latched)
        self.assertFalse(latched_after_spike)
        self.assertLess(filtered, 180000.0)

    def test_person_area_latch_confirms_stop_and_release(self) -> None:
        latch = PersonAreaLatch(
            stop_area=180000.0,
            resume_area=140000.0,
            window_size=1,
            stop_confirm_frames=2,
            resume_confirm_frames=2,
        )
        large = PersonDetection(
            **{**self.make_detection(320).__dict__, "width": 500, "height": 400}
        )
        small = self.make_detection(320)

        self.assertFalse(latch.update(large)[0])
        self.assertTrue(latch.update(large)[0])
        self.assertTrue(latch.update(small)[0])
        self.assertFalse(latch.update(small)[0])

    def test_disabled_person_area_stop_still_reports_filtered_area(self) -> None:
        latch = PersonAreaLatch(stop_area=0, window_size=3)

        latched, filtered = latch.update(self.make_detection(320))

        self.assertFalse(latched)
        self.assertEqual(filtered, 28000.0)
