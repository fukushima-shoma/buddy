from __future__ import annotations

import argparse
from pathlib import Path
import time

from robot.distance import (
    DistanceSensor,
    MockDistanceSensor,
    ObstacleLatch,
    retain_recent_distance,
    update_distance_median,
)
from robot.person_detection import (
    HogPersonDetector,
    HOG_DEFAULT_CONFIDENCE,
    MEDIAPIPE_DEFAULT_CONFIDENCE,
    MediaPipePersonDetector,
    PersonAreaLatch,
    PersonDetection,
    PersonDetectionStabilizer,
    save_annotated_image,
)
from robot.picamera2_driver import Picamera2FrameSource
from robot.motor import BuddyDrive, MotorCommand
from robot.motor_cli import create_driver


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Follow a person with distance-based safety stops."
    )
    parser.add_argument(
        "--backend",
        choices=("mock", "gpiozero"),
        default="mock",
        help="Motor backend. gpiozero must only be used with raised wheels first.",
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
    parser.add_argument("--distance-window", type=int, default=3)
    parser.add_argument("--stop-distance", type=float, default=60.0)
    parser.add_argument("--resume-distance", type=float, default=70.0)
    parser.add_argument("--resume-confirm-frames", type=int, default=5)
    parser.add_argument("--stop-person-area", type=float, default=0.0)
    parser.add_argument("--resume-person-area", type=float, default=140000.0)
    parser.add_argument("--person-area-window", type=int, default=3)
    parser.add_argument("--person-area-stop-confirm-frames", type=int, default=2)
    parser.add_argument("--person-area-resume-confirm-frames", type=int, default=3)
    parser.add_argument("--distance-mode", choices=(1, 2), type=int, default=2)
    parser.add_argument("--person-confirm-window", type=int, default=3)
    parser.add_argument("--person-confirm-hits", type=int, default=2)
    parser.add_argument("--person-confirm-max-shift", type=int, default=160)
    parser.add_argument("--lost-frame-tolerance", type=int, default=1)
    parser.add_argument("--position-window", type=int, default=3)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--turn-speed", type=float, default=1.0)
    parser.add_argument("--turn-pulse", type=float, default=0.08)
    parser.add_argument("--max-speed", type=float, default=1.0)
    parser.add_argument("--left-scale", type=float, default=0.95)
    parser.add_argument("--right-scale", type=float, default=1.0)
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
    person_confirming: bool = False,
    person_too_close: bool = False,
) -> tuple[str, str]:
    if distance_required and distance_cm is None:
        return "stop", "distance-not-ready"
    if distance_required and obstacle_latched:
        return "stop", "obstacle"
    if detection is None:
        if person_confirming:
            return "stop", "person-confirming"
        return "stop", "not-found"
    if person_too_close:
        return "stop", "person-too-close"
    if detection.position in ("left", "right"):
        return detection.position, "tracking"
    return "forward", "tracking"


def apply_person_action(
    drive: BuddyDrive,
    action: str,
    speed: float,
    turn_speed: float,
) -> MotorCommand:
    if action == "stop":
        return drive.stop()
    if action == "forward":
        return drive.forward(speed)
    if action in ("left", "right"):
        return getattr(drive, action)(turn_speed)
    raise ValueError(f"Unsupported person tracking action: {action}")


def create_person_detector(
    args: argparse.Namespace,
) -> HogPersonDetector | MediaPipePersonDetector:
    if args.person_backend == "hog":
        confidence = (
            HOG_DEFAULT_CONFIDENCE
            if args.min_confidence is None
            else args.min_confidence
        )
        return HogPersonDetector(min_confidence=confidence, scale=args.scale)
    confidence = (
        MEDIAPIPE_DEFAULT_CONFIDENCE
        if args.min_confidence is None
        else args.min_confidence
    )
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
    driver = create_driver(args.backend)
    drive = BuddyDrive(
        driver,
        max_speed=args.max_speed,
        left_scale=args.left_scale,
        right_scale=args.right_scale,
    )
    started_at = time.monotonic()
    last_report_at = 0.0
    last_status: tuple[str, str, str] | None = None
    last_annotated = None
    last_distance_cm: float | None = None
    last_distance_at: float | None = None
    recent_distances_cm: tuple[float, ...] = ()
    obstacle_latch = ObstacleLatch(
        stop_distance_cm=args.stop_distance,
        resume_distance_cm=args.resume_distance,
        resume_confirm_frames=args.resume_confirm_frames,
    )
    stabilizer = PersonDetectionStabilizer(
        image_width=args.width,
        confirm_window=args.person_confirm_window,
        confirm_hits=args.person_confirm_hits,
        confirm_max_shift=args.person_confirm_max_shift,
        lost_frame_tolerance=args.lost_frame_tolerance,
        position_window=args.position_window,
    )
    person_area_latch = PersonAreaLatch(
        stop_area=args.stop_person_area,
        resume_area=args.resume_person_area,
        window_size=args.person_area_window,
        stop_confirm_frames=args.person_area_stop_confirm_frames,
        resume_confirm_frames=args.person_area_resume_confirm_frames,
    )
    last_motor_action = ""
    frame_interval = 1.0 / max(0.1, args.fps)

    print(
        f"backend={args.backend} person-backend={args.person_backend} "
        f"distance-backend={args.distance_backend} Ctrl+C: stop"
    )
    try:
        source.start()
        distance_sensor.start()
        while args.duration <= 0 or time.monotonic() - started_at < args.duration:
            frame_started_at = time.monotonic()
            frame = source.capture_array()
            measured_detection, last_annotated = detector.detect(frame)
            detection, person_confirming = stabilizer.update(measured_detection)
            person_too_close, filtered_person_area = person_area_latch.update(
                detection
            )
            measured_distance_cm = distance_sensor.read_distance_cm()
            filtered_distance_cm, recent_distances_cm = update_distance_median(
                measured_distance_cm,
                recent_distances_cm,
                args.distance_window,
            )
            distance_cm, last_distance_at = retain_recent_distance(
                filtered_distance_cm,
                last_distance_cm,
                last_distance_at,
                time.monotonic(),
            )
            if distance_cm is not None:
                last_distance_cm = distance_cm
            obstacle_latched = obstacle_latch.update(
                distance_cm,
                raw_distance_cm=measured_distance_cm,
            )
            action, reason = person_tracking_decision(
                detection,
                distance_cm,
                distance_required=True,
                obstacle_latched=obstacle_latched,
                person_confirming=person_confirming,
                person_too_close=person_too_close,
            )
            if action in ("left", "right") and args.turn_pulse > 0:
                apply_person_action(drive, action, args.speed, args.turn_speed)
                time.sleep(max(0.0, args.turn_pulse))
                drive.stop()
                last_motor_action = ""
            elif action != last_motor_action:
                apply_person_action(drive, action, args.speed, args.turn_speed)
                last_motor_action = action
            if person_confirming:
                position = "confirming"
                reported_detection = measured_detection
            else:
                position = "not-found" if detection is None else detection.position
                reported_detection = detection
            status = (action, reason, position)
            now = time.monotonic()
            if status != last_status or now - last_report_at >= 1.0:
                confidence = (
                    "not-found"
                    if reported_detection is None
                    else f"{reported_detection.confidence:.2f}"
                )
                raw_person_area = (
                    0
                    if reported_detection is None
                    else reported_detection.width * reported_detection.height
                )
                person_area_text = (
                    "not-ready"
                    if filtered_person_area is None
                    else f"{filtered_person_area:.0f}"
                )
                distance_text = (
                    "not-ready"
                    if distance_cm is None
                    else f"{distance_cm:.1f}cm"
                )
                raw_distance_text = (
                    "not-ready"
                    if measured_distance_cm is None
                    else f"{measured_distance_cm:.1f}cm"
                )
                print(
                    f"person={position} action={action} reason={reason} "
                    f"confidence={confidence} raw-area={raw_person_area} "
                    f"area={person_area_text} raw-distance={raw_distance_text} "
                    f"distance={distance_text}",
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
        drive.stop()
        distance_sensor.close()
        source.close()
        drive.close()

    if last_annotated is not None:
        save_annotated_image(args.output, last_annotated)
        print(f"snapshot={args.output.expanduser()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
