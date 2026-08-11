from __future__ import annotations

import argparse
import time

from robot.distance import DistanceSensor, MockDistanceSensor, obstacle_detected


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Measure distance with Buddy's sensor.")
    parser.add_argument(
        "--backend",
        choices=("mock", "vl53l1x"),
        default="mock",
        help="Use vl53l1x only when the I2C sensor is connected.",
    )
    parser.add_argument("--stop-distance", type=float, default=20.0)
    parser.add_argument("--duration", type=float, default=15.0)
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--distance-mode", choices=(1, 2), type=int, default=2)
    parser.add_argument(
        "--timing-budget",
        choices=(20, 33, 50, 100, 200, 500),
        type=int,
        default=100,
    )
    parser.add_argument("--mock-distance", type=float, default=100.0)
    return parser


def create_sensor(args: argparse.Namespace) -> DistanceSensor:
    if args.backend == "mock":
        return MockDistanceSensor(args.mock_distance)
    if args.backend == "vl53l1x":
        from robot.vl53l1x_driver import Vl53l1xDistanceSensor

        return Vl53l1xDistanceSensor(
            distance_mode=args.distance_mode,
            timing_budget_ms=args.timing_budget,
        )
    raise ValueError(f"Unsupported backend: {args.backend}")


def run_monitor(
    sensor: DistanceSensor,
    *,
    stop_distance_cm: float,
    duration: float,
    interval: float,
) -> None:
    started_at = time.monotonic()
    try:
        sensor.start()
        while duration <= 0 or time.monotonic() - started_at < duration:
            distance = sensor.read_distance_cm()
            if distance is not None:
                obstacle = obstacle_detected(distance, stop_distance_cm)
                print(
                    f"distance={distance:.1f}cm "
                    f"obstacle={str(obstacle).lower()}",
                    flush=True,
                )
            time.sleep(max(0.01, interval))
    finally:
        sensor.close()


def main() -> int:
    args = build_parser().parse_args()
    sensor = create_sensor(args)
    print(
        f"backend={args.backend} stop-distance={args.stop_distance:.1f}cm "
        "Ctrl+C: stop",
        flush=True,
    )
    try:
        run_monitor(
            sensor,
            stop_distance_cm=args.stop_distance,
            duration=args.duration,
            interval=args.interval,
        )
    except KeyboardInterrupt:
        print("Stopping distance measurement.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
