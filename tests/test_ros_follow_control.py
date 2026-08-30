import unittest

from buddy_ros.follow_control import decide_follow_command
from buddy_ros.person_control import PersonTarget


class RosFollowControlTest(unittest.TestCase):
    def make_target(self, position: str = "center") -> PersonTarget:
        return PersonTarget(
            status="detected",
            detected=True,
            position=position,
            confidence=0.9,
            center_x=320,
            center_y=240,
            x=220,
            y=80,
            width=200,
            height=320,
            image_width=640,
            image_height=480,
        )

    def test_disabled_following_stops(self) -> None:
        command = decide_follow_command(
            self.make_target(),
            2.0,
            enabled=False,
            obstacle_latched=False,
        )

        self.assertEqual((command.action, command.reason), ("stop", "disabled"))

    def test_obstacle_has_priority(self) -> None:
        command = decide_follow_command(
            self.make_target("left"),
            0.3,
            enabled=True,
            obstacle_latched=True,
        )

        self.assertEqual((command.action, command.reason), ("stop", "obstacle"))

    def test_power_safety_stop_precedes_tracking(self) -> None:
        command = decide_follow_command(
            self.make_target(),
            2.0,
            enabled=True,
            obstacle_latched=False,
            safety_stop_reason="power-low",
        )

        self.assertEqual((command.action, command.reason), ("stop", "power-low"))

    def test_center_target_moves_forward(self) -> None:
        command = decide_follow_command(
            self.make_target(),
            2.0,
            enabled=True,
            obstacle_latched=False,
        )

        self.assertEqual(command.action, "forward")
        self.assertEqual(command.linear_x, 0.3)
        self.assertEqual(command.angular_z, 0.0)

    def test_left_and_right_targets_turn_in_place(self) -> None:
        left = decide_follow_command(
            self.make_target("left"),
            2.0,
            enabled=True,
            obstacle_latched=False,
        )
        right = decide_follow_command(
            self.make_target("right"),
            2.0,
            enabled=True,
            obstacle_latched=False,
        )

        self.assertGreater(left.angular_z, 0.0)
        self.assertLess(right.angular_z, 0.0)

    def test_missing_distance_only_allows_turning(self) -> None:
        center = decide_follow_command(
            self.make_target("center"),
            None,
            enabled=True,
            obstacle_latched=False,
        )
        left = decide_follow_command(
            self.make_target("left"),
            None,
            enabled=True,
            obstacle_latched=False,
        )

        self.assertEqual(center.reason, "distance-not-ready")
        self.assertEqual(left.reason, "distance-not-ready-turning")
        self.assertEqual(left.action, "left")

    def test_not_found_and_confirming_targets_stop(self) -> None:
        missing = PersonTarget(
            **{
                **self.make_target().__dict__,
                "status": "not-found",
                "detected": False,
            }
        )
        confirming = PersonTarget(
            **{
                **self.make_target().__dict__,
                "status": "confirming",
                "detected": False,
            }
        )

        self.assertEqual(
            decide_follow_command(
                missing,
                2.0,
                enabled=True,
                obstacle_latched=False,
            ).reason,
            "not-found",
        )
        self.assertEqual(
            decide_follow_command(
                confirming,
                2.0,
                enabled=True,
                obstacle_latched=False,
            ).reason,
            "person-confirming",
        )


if __name__ == "__main__":
    unittest.main()
