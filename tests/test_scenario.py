import json
from math import pi
import unittest

from buddy_ros.follow_control import FollowCoordinator
from buddy_ros.odometry_control import DifferentialDriveGeometry, EncoderOdometry
from buddy_ros.scenario import ScenarioRunner, replay_json_lines


def make_runner(*, require_power: bool = False) -> ScenarioRunner:
    return ScenarioRunner(
        follow=FollowCoordinator(require_power_status=require_power),
        odometry=EncoderOdometry(
            DifferentialDriveGeometry(0.07, 0.10, 20),
        ),
    )


class ScenarioTest(unittest.TestCase):
    def test_replay_combines_follow_safety_and_encoder_odometry(self) -> None:
        events = [
            {"at": 0.0, "type": "enable", "enabled": True},
            {"at": 0.0, "type": "person", "position": "center"},
            {"at": 0.0, "type": "distance", "meters": 2.0},
            {"at": 0.0, "type": "encoder", "left": 0, "right": 0},
            {"at": 0.1, "type": "encoder", "left": 20, "right": 20},
        ]

        results = replay_json_lines(
            (json.dumps(event) for event in events),
            make_runner(),
        )

        self.assertEqual(results[-1]["follow"]["action"], "forward")
        self.assertAlmostEqual(results[-1]["pose"]["x"], pi * 0.07)

    def test_scenario_can_inject_obstacle_and_power_failures(self) -> None:
        runner = make_runner(require_power=True)
        runner.apply({"at": 0, "type": "enable"})
        runner.apply({"at": 0, "type": "person", "position": "center"})
        runner.apply({"at": 0, "type": "distance", "meters": 2})
        low_power = runner.apply({"at": 0, "type": "power", "good": False})
        obstacle = runner.apply({"at": 0.1, "type": "distance", "meters": 0.2})

        self.assertEqual(low_power["follow"]["reason"], "power-low")
        self.assertEqual(obstacle["follow"]["reason"], "power-low")
        runner.apply({"at": 0.1, "type": "power", "good": True})
        self.assertEqual(
            runner.apply({"at": 0.2, "type": "sample"})["follow"]["reason"],
            "obstacle",
        )

    def test_stale_inputs_stop_at_sample_event(self) -> None:
        runner = make_runner()
        runner.apply({"at": 0, "type": "enable"})
        runner.apply({"at": 0, "type": "person", "position": "left"})
        runner.apply({"at": 0, "type": "distance", "meters": 2})

        result = runner.apply({"at": 1, "type": "sample"})

        self.assertEqual(result["follow"]["reason"], "person-not-ready")

    def test_invalid_line_reports_source_line_number(self) -> None:
        with self.assertRaisesRegex(ValueError, "line 2"):
            replay_json_lines(
                ["# comment\n", '{"at": 0, "type": "unknown"}\n'],
                make_runner(),
            )

    def test_timestamps_cannot_go_backwards(self) -> None:
        runner = make_runner()
        runner.apply({"at": 2, "type": "sample"})
        with self.assertRaisesRegex(ValueError, "line 1"):
            replay_json_lines(
                ['{"at": 1, "type": "sample"}\n'],
                runner,
            )


if __name__ == "__main__":
    unittest.main()
