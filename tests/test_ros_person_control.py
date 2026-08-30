import json
import unittest

from buddy_ros.person_control import PersonTarget, person_target_from_detection
from buddy_ros.person_node import create_detector
from robot.person_detection import PersonDetection


class RosPersonControlTest(unittest.TestCase):
    def make_detection(self) -> PersonDetection:
        return PersonDetection(
            confidence=0.91,
            center_x=320,
            center_y=240,
            x=220,
            y=80,
            width=200,
            height=320,
            position="center",
        )

    def test_detection_is_serialized_as_one_target_message(self) -> None:
        target = person_target_from_detection(
            self.make_detection(),
            image_width=640,
            image_height=480,
        )
        payload = json.loads(target.to_json())

        self.assertTrue(payload["detected"])
        self.assertEqual(payload["status"], "detected")
        self.assertEqual(payload["position"], "center")
        self.assertEqual(payload["confidence"], 0.91)
        self.assertEqual(payload["width"], 200)
        self.assertEqual(payload["image_width"], 640)

        restored = PersonTarget.from_json(target.to_json())
        self.assertEqual(restored, target)

    def test_missing_detection_has_explicit_not_found_state(self) -> None:
        target = person_target_from_detection(
            None,
            image_width=640,
            image_height=480,
        )

        self.assertFalse(target.detected)
        self.assertEqual(target.status, "not-found")
        self.assertEqual(target.width, 0)

    def test_acquisition_state_is_preserved(self) -> None:
        target = person_target_from_detection(
            None,
            image_width=640,
            image_height=480,
            confirming=True,
        )

        self.assertEqual(target.status, "confirming")

    def test_unknown_detector_backend_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            create_detector("unknown")

    def test_invalid_target_payload_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PersonTarget.from_json('{"detected":true}')


if __name__ == "__main__":
    unittest.main()
