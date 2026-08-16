from __future__ import annotations

import argparse
import time

from robot.color_detection import HSV_RANGES, ColorDetection, detect_color_frame
from robot.distance import DistanceSensor, MockDistanceSensor, obstacle_detected
from robot.motor import BuddyDrive, MotorCommand
from robot.motor_cli import create_driver
from robot.picamera2_driver import Picamera2FrameSource


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Follow a colored object with Buddy's camera and motors."
    )
    parser.add_argument("--color", choices=tuple(HSV_RANGES), default="red")
    parser.add_argument("--duration", type=float, default=15.0)
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--min-area", type=float, default=50.0)
    parser.add_argument(
        "--stop-area",
        type=float,
        default=250000.0,
        help="Stop when the detected area reaches this size. Default: 250000.",
    )
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--turn-speed", type=float, default=1.0)
    parser.add_argument(
        "--turn-pulse",
        type=float,
        default=0.08,
        help="Seconds to turn before stopping and checking the next frame.",
    )
    parser.add_argument("--max-speed", type=float, default=1.0)
    parser.add_argument("--left-scale", type=float, default=0.95)
    parser.add_argument("--right-scale", type=float, default=1.0)
    parser.add_argument(
        "--distance-backend",
        choices=("none", "mock", "vl53l1x"),
        default="none",
        help="Optional distance sensor used as the highest-priority stop input.",
    )
    parser.add_argument("--stop-distance", type=float, default=60.0)
    parser.add_argument(
        "--resume-distance",
        type=float,
        default=70.0,
        help="After an obstacle stop, resume at or beyond this distance.",
    )
    parser.add_argument("--mock-distance", type=float, default=100.0)
    parser.add_argument(
        "--lost-frame-tolerance",
        type=int,
        default=1,
        help="Reuse the last detection for this many missed frames.",
    )
    parser.add_argument("--distance-mode", choices=(1, 2), type=int, default=2)
    parser.add_argument(
        "--timing-budget",
        choices=(20, 33, 50, 100, 200, 500),
        type=int,
        default=100,
    )
    parser.add_argument(
        "--backend",
        choices=("mock", "gpiozero"),
        default="mock",
        help="Use gpiozero only after testing with the wheels raised.",
    )
    return parser


def tracking_decision(
    detection: ColorDetection | None,
    stop_area: float,
    distance_cm: float | None = None,
    stop_distance_cm: float = 20.0,
    distance_required: bool = False,
    obstacle_latched: bool = False,
) -> tuple[str, str]:
    if distance_required and distance_cm is None:
        return "stop", "distance-not-ready"
    if distance_required and (
        obstacle_latched or obstacle_detected(distance_cm, stop_distance_cm)
    ):
        return "stop", "obstacle"
    if detection is None:
        return "stop", "not-found"
    if detection.area >= max(0.0, stop_area):
        return "stop", "too-close"
    if detection.position in ("left", "right"):
        return detection.position, "tracking"
    return "forward", "tracking"


def retain_recent_distance(
    measured_distance_cm: float | None,
    previous_distance_cm: float | None,
    previous_measurement_at: float | None,
    now: float,
    stale_after: float = 0.5,
) -> tuple[float | None, float | None]:
    """Keep the latest valid reading between VL53L1X measurement cycles."""
    if measured_distance_cm is not None:
        return measured_distance_cm, now
    if (
        previous_distance_cm is not None
        and previous_measurement_at is not None
        and now - previous_measurement_at <= stale_after
    ):
        return previous_distance_cm, previous_measurement_at
    return None, previous_measurement_at


def retain_recent_detection(
    detection: ColorDetection | None,
    previous_detection: ColorDetection | None,
    missed_frames: int,
    tolerance: int,
) -> tuple[ColorDetection | None, ColorDetection | None, int]:
    """Ignore a short detection dropout without hiding a sustained loss."""
    if detection is not None:
        return detection, detection, 0
    missed_frames += 1
    if previous_detection is not None and missed_frames <= max(0, tolerance):
        return previous_detection, previous_detection, missed_frames
    return None, None, missed_frames


def update_obstacle_latch(
    distance_cm: float | None,
    stop_distance_cm: float,
    resume_distance_cm: float,
    obstacle_latched: bool,
) -> bool:
    """Latch an obstacle stop until the path has a safe clearance margin."""
    if distance_cm is None:
        return obstacle_latched
    stop_distance_cm = max(0.0, stop_distance_cm)
    resume_distance_cm = max(stop_distance_cm, resume_distance_cm)
    if obstacle_latched:
        return distance_cm < resume_distance_cm
    return distance_cm <= stop_distance_cm


def action_for_detection(
    detection: ColorDetection | None,
    stop_area: float = 30000.0,
) -> str:
    return tracking_decision(detection, stop_area)[0]


def apply_tracking_action(
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
    raise ValueError(f"Unsupported tracking action: {action}")


def run_color_follow(
    source: Picamera2FrameSource,
    drive: BuddyDrive,
    *,
    color: str,
    duration: float,
    fps: float,
    min_area: float,
    stop_area: float,
    speed: float,
    turn_speed: float,
    turn_pulse: float,
    lost_frame_tolerance: int,
    distance_sensor: DistanceSensor | None = None,
    stop_distance_cm: float = 20.0,
    resume_distance_cm: float = 30.0,
) -> None:
    started_at = time.monotonic()
    last_action = ""
    last_report_at = 0.0
    last_distance_cm: float | None = None
    last_distance_at: float | None = None
    last_detection: ColorDetection | None = None
    missed_detection_frames = 0
    obstacle_latched = False
    frame_interval = 1.0 / max(0.1, fps)

    try:
        source.start()
        if distance_sensor is not None:
            distance_sensor.start()
        while duration <= 0 or time.monotonic() - started_at < duration:
            frame_started_at = time.monotonic()
            frame = source.capture_array()
            measured_detection, _ = detect_color_frame(
                frame, color, min_area=min_area
            )
            detection, last_detection, missed_detection_frames = (
                retain_recent_detection(
                    measured_detection,
                    last_detection,
                    missed_detection_frames,
                    lost_frame_tolerance,
                )
            )
            measured_distance_cm = (
                None
                if distance_sensor is None
                else distance_sensor.read_distance_cm()
            )
            if distance_sensor is None:
                distance_cm = None
            else:
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
                stop_distance_cm,
                resume_distance_cm,
                obstacle_latched,
            )
            action, reason = tracking_decision(
                detection,
                stop_area,
                distance_cm=distance_cm,
                stop_distance_cm=stop_distance_cm,
                distance_required=distance_sensor is not None,
                obstacle_latched=obstacle_latched,
            )

            if action in ("left", "right") and turn_pulse > 0:
                command = apply_tracking_action(drive, action, speed, turn_speed)
                time.sleep(max(0.0, turn_pulse))
                drive.stop()
                last_action = ""
            elif action != last_action:
                command = apply_tracking_action(drive, action, speed, turn_speed)
                last_action = action
            else:
                command = None

            now = time.monotonic()
            if command is not None or now - last_report_at >= 1.0:
                area = 0 if detection is None else detection.area
                distance_text = (
                    "off"
                    if distance_sensor is None
                    else "not-ready" if distance_cm is None else f"{distance_cm:.1f}cm"
                )
                print(
                    f"color={color} action={action} reason={reason} "
                    f"area={area:.0f} distance={distance_text}",
                    flush=True,
                )
                last_report_at = now

            remaining = frame_interval - (time.monotonic() - frame_started_at)
            if remaining > 0:
                time.sleep(remaining)
    finally:
        drive.stop()
        if distance_sensor is not None:
            distance_sensor.close()


def create_distance_sensor(args: argparse.Namespace) -> DistanceSensor | None:
    if args.distance_backend == "none":
        return None
    if args.distance_backend == "mock":
        return MockDistanceSensor(args.mock_distance)
    if args.distance_backend == "vl53l1x":
        from robot.vl53l1x_driver import Vl53l1xDistanceSensor

        return Vl53l1xDistanceSensor(
            distance_mode=args.distance_mode,
            timing_budget_ms=args.timing_budget,
        )
    raise ValueError(f"Unsupported distance backend: {args.distance_backend}")


def main() -> int:
    args = build_parser().parse_args()
    source = Picamera2FrameSource(width=args.width, height=args.height)
    driver = create_driver(args.backend)
    drive = BuddyDrive(
        driver,
        max_speed=args.max_speed,
        left_scale=args.left_scale,
        right_scale=args.right_scale,
    )
    distance_sensor = create_distance_sensor(args)

    print(
        f"backend={args.backend} distance-backend={args.distance_backend} "
        f"tracking={args.color} Ctrl+C: stop"
    )
    try:
        run_color_follow(
            source,
            drive,
            color=args.color,
            duration=args.duration,
            fps=args.fps,
            min_area=args.min_area,
            stop_area=args.stop_area,
            speed=args.speed,
            turn_speed=args.turn_speed,
            turn_pulse=args.turn_pulse,
            lost_frame_tolerance=args.lost_frame_tolerance,
            distance_sensor=distance_sensor,
            stop_distance_cm=args.stop_distance,
            resume_distance_cm=args.resume_distance,
        )
    except KeyboardInterrupt:
        print("Stopping color follow.")
    finally:
        drive.stop()
        source.close()
        drive.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
