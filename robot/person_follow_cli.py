from __future__ import annotations

import argparse
from pathlib import Path
import time

from robot.distance import (
    DistanceSensor,
    MockDistanceSensor,
    retain_recent_distance,
    update_obstacle_latch,
)
from robot.person_detection import (
    HogPersonDetector,
    MediaPipePersonDetector,
    PersonDetection,
    save_annotated_image,
)
from robot.picamera2_driver import Picamera2FrameSource


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Combine person and distance detection without moving motors."
    )
    parser.add_argument(
        "--person-backend",
        choices=("mediapipe", "hog"),
        default="mediapipe",
    )
    parser.add_argument(
        "--distance-backend",
        choices=("mock", "vl53l1x"),
        default="mock",
    )
    parser.add_argument("--duration", type=float, default=15.0)
    parser.add_argument("--fps", type=float, default=5.0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--min-confidence", type=float)
    parser.add_argument("--scale", type=float, default=1.05)
    parser.add_argument("--mock-distance", type=float, default=100.0)
    parser.add_argument("--stop-distance", type=float, default=60.0)
    parser.add_argument("--resume-distance", type=float, default=70.0)
    parser.add_argument("--distance-mode", choices=(1, 2), type=int, default=2)
    parser.add_argument(
        "--timing-budget",
        choices=(20, 33, 50, 100, 200, 500),
        type=int,
        default=100,
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=Path(
            "models/person_detection/person_detection_mediapipe_2023mar.onnx"
        ),
    )
    parser.add_argument(
        "--model-helper",
        type=Path,
        default=Path("models/person_detection/mp_persondet.py"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("captures/person-follow.jpg"),
    )
    return parser


def person_tracking_decision(
    detection: PersonDetection | None,
    distance_cm: float | None,
    *,
    distance_required: bool,
    obstacle_latched: bool,
) -> tuple[str, str]:
    if distance_required and distance_cm is None:
        return "stop", "distance-not-ready"
    if distance_required and obstacle_latched:
        return "stop", "obstacle"
    if detection is None:
        return "stop", "not-found"
    if detection.position in ("left", "right"):
        return detection.position, "tracking"
    return "forward", "tracking"


def create_person_detector(
    args: argparse.Namespace,
) -> HogPersonDetector | MediaPipePersonDetector:
    if args.person_backend == "hog":
        confidence = 0.2 if args.min_confidence is None else args.min_confidence
        return HogPersonDetector(min_confidence=confidence, scale=args.scale)
    confidence = 0.5 if args.min_confidence is None else args.min_confidence
    return MediaPipePersonDetector(
        model_path=args.model,
        helper_path=args.model_helper,
        min_confidence=confidence,
    )


def create_distance_sensor(args: argparse.Namespace) -> DistanceSensor:
    if args.distance_backend == "mock":
        return MockDistanceSensor(args.mock_distance)
    from robot.vl53l1x_driver import Vl53l1xDistanceSensor

    return Vl53l1xDistanceSensor(
        distance_mode=args.distance_mode,
        timing_budget_ms=args.timing_budget,
    )


def main() -> int:
    args = build_parser().parse_args()
    detector = create_person_detector(args)
    distance_sensor = create_distance_sensor(args)
    source = Picamera2FrameSource(width=args.width, height=args.height)
    started_at = time.monotonic()
    last_report_at = 0.0
    last_status: tuple[str, str, str] | None = None
    last_annotated = None
    last_distance_cm: float | None = None
    last_distance_at: float | None = None
    obstacle_latched = False
    frame_interval = 1.0 / max(0.1, args.fps)

    print(
        f"motor=off person-backend={args.person_backend} "
        f"distance-backend={args.distance_backend} Ctrl+C: stop"
    )
    try:
        source.start()
        distance_sensor.start()
        while args.duration <= 0 or time.monotonic() - started_at < args.duration:
            frame_started_at = time.monotonic()
            frame = source.capture_array()
            detection, last_annotated = detector.detect(frame)
            measured_distance_cm = distance_sensor.read_distance_cm()
            distance_cm, last_distance_at = retain_recent_distance(
                measured_distance_cm,
                last_distance_cm,
                last_distance_at,
                time.monotonic(),
            )
            if distance_cm is not None:
                last_distance_cm = distance_cm
            obstacle_latched = update_obstacle_latch(
                distance_cm,
                args.stop_distance,
                args.resume_distance,
                obstacle_latched,
            )
            action, reason = person_tracking_decision(
                detection,
                distance_cm,
                distance_required=True,
                obstacle_latched=obstacle_latched,
            )
            position = "not-found" if detection is None else detection.position
            status = (action, reason, position)
            now = time.monotonic()
            if status != last_status or now - last_report_at >= 1.0:
                confidence = (
                    "not-found"
                    if detection is None
                    else f"{detection.confidence:.2f}"
                )
                distance_text = (
                    "not-ready"
                    if distance_cm is None
                    else f"{distance_cm:.1f}cm"
                )
                print(
                    f"person={position} action={action} reason={reason} "
                    f"confidence={confidence} distance={distance_text}",
                    flush=True,
                )
                last_status = status
                last_report_at = now

            remaining = frame_interval - (time.monotonic() - frame_started_at)
            if remaining > 0:
                time.sleep(remaining)
    except KeyboardInterrupt:
        print("Stopping person follow decision.")
    finally:
        distance_sensor.close()
        source.close()

    if last_annotated is not None:
        save_annotated_image(args.output, last_annotated)
        print(f"snapshot={args.output.expanduser()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
