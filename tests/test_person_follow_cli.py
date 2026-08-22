import unittest

from robot.person_detection import PersonDetection
from robot.person_follow_cli import (
    build_parser,
    create_distance_sensor,
    person_tracking_decision,
)


def detection(position: str) -> PersonDetection:
    return PersonDetection(
        confidence=0.9,
        center_x=320,
        center_y=240,
        x=220,
        y=80,
        width=200,
        height=320,
        position=position,
    )


class PersonFollowCliTest(unittest.TestCase):
    def test_missing_person_stops(self) -> None:
        self.assertEqual(
            person_tracking_decision(
                None,
                100.0,
                distance_required=True,
                obstacle_latched=False,
            ),
            ("stop", "not-found"),
        )

    def test_person_position_selects_action(self) -> None:
        self.assertEqual(
            person_tracking_decision(
                detection("left"),
                100.0,
                distance_required=True,
                obstacle_latched=False,
            ),
            ("left", "tracking"),
        )
        self.assertEqual(
            person_tracking_decision(
                detection("center"),
                100.0,
                distance_required=True,
                obstacle_latched=False,
            ),
            ("forward", "tracking"),
        )

    def test_obstacle_and_missing_distance_stop_before_tracking(self) -> None:
        person = detection("center")
        self.assertEqual(
            person_tracking_decision(
                person,
                55.0,
                distance_required=True,
                obstacle_latched=True,
            ),
            ("stop", "obstacle"),
        )
        self.assertEqual(
            person_tracking_decision(
                person,
                None,
                distance_required=True,
                obstacle_latched=False,
            ),
            ("stop", "distance-not-ready"),
        )

    def test_defaults_keep_motors_off_and_use_mock_distance(self) -> None:
        args = build_parser().parse_args([])

        self.assertEqual(args.person_backend, "mediapipe")
        self.assertEqual(args.distance_backend, "mock")
        self.assertEqual(args.stop_distance, 60.0)
        self.assertEqual(args.resume_distance, 70.0)
        self.assertEqual(args.resume_confirm_frames, 5)
        self.assertEqual(args.stop_person_area, 0.0)
        self.assertEqual(args.resume_person_area, 140000.0)
        self.assertEqual(args.person_area_window, 3)
        self.assertEqual(args.person_area_stop_confirm_frames, 2)
        self.assertEqual(args.person_area_resume_confirm_frames, 3)
        self.assertEqual(args.distance_window, 3)
        self.assertEqual(args.person_confirm_frames, 3)
        self.assertEqual(args.lost_frame_tolerance, 1)
        self.assertEqual(args.position_window, 3)
        self.assertEqual(create_distance_sensor(args).read_distance_cm(), 100.0)

    def test_unconfirmed_person_stops_safely(self) -> None:
        self.assertEqual(
            person_tracking_decision(
                None,
                100.0,
                distance_required=True,
                obstacle_latched=False,
                person_confirming=True,
            ),
            ("stop", "person-confirming"),
        )

    def test_large_person_detection_stops_as_visual_fallback(self) -> None:
        close_person = PersonDetection(
            confidence=0.9,
            center_x=320,
            center_y=240,
            x=70,
            y=40,
            width=500,
            height=400,
            position="center",
        )

        self.assertEqual(
            person_tracking_decision(
                close_person,
                100.0,
                distance_required=True,
                obstacle_latched=False,
                person_too_close=True,
            ),
            ("stop", "person-too-close"),
        )


if __name__ == "__main__":
    unittest.main()
