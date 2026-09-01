from __future__ import annotations

import argparse
import json
from pathlib import Path

from buddy_ros.follow_control import FollowCoordinator
from buddy_ros.odometry_control import DifferentialDriveGeometry, EncoderOdometry
from buddy_ros.scenario import ScenarioRunner, replay_json_lines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay numeric Buddy sensor events without hardware.",
    )
    parser.add_argument("scenario", type=Path)
    parser.add_argument("--wheel-diameter", type=float, required=True)
    parser.add_argument("--wheel-separation", type=float, required=True)
    parser.add_argument("--ticks-per-revolution", type=int, required=True)
    parser.add_argument("--require-power", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    runner = ScenarioRunner(
        follow=FollowCoordinator(require_power_status=args.require_power),
        odometry=EncoderOdometry(
            DifferentialDriveGeometry(
                wheel_diameter_m=args.wheel_diameter,
                wheel_separation_m=args.wheel_separation,
                ticks_per_revolution=args.ticks_per_revolution,
            )
        ),
    )
    with args.scenario.open(encoding="utf-8") as source:
        for result in replay_json_lines(source, runner):
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
