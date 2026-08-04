from __future__ import annotations

import argparse
import time

from robot.color_detection import HSV_RANGES, ColorDetection, detect_color_frame
from robot.motor import BuddyDrive, MotorCommand
from robot.motor_cli import create_driver
from robot.picamera2_driver import Picamera2FrameSource


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Follow a colored object with Buddy's camera and motors."
    )
    parser.add_argument("--color", choices=tuple(HSV_RANGES), default="red")
    parser.add_argument("--duration", type=float, default=15.0)
    parser.add_argument("--fps", type=float, default=5.0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--min-area", type=float, default=1000.0)
    parser.add_argument(
        "--stop-area",
        type=float,
        default=30000.0,
        help="Stop when the detected area reaches this size. Default: 30000.",
    )
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--turn-speed", type=float, default=1.0)
    parser.add_argument("--max-speed", type=float, default=1.0)
    parser.add_argument("--left-scale", type=float, default=0.95)
    parser.add_argument("--right-scale", type=float, default=1.0)
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
) -> tuple[str, str]:
    if detection is None:
        return "stop", "not-found"
    if detection.area >= max(0.0, stop_area):
        return "stop", "too-close"
    if detection.position in ("left", "right"):
        return detection.position, "tracking"
    return "forward", "tracking"


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
) -> None:
    started_at = time.monotonic()
    last_action = ""
    last_report_at = 0.0
    frame_interval = 1.0 / max(0.1, fps)

    source.start()
    try:
        while duration <= 0 or time.monotonic() - started_at < duration:
            frame_started_at = time.monotonic()
            frame = source.capture_array()
            detection, _ = detect_color_frame(frame, color, min_area=min_area)
            action, reason = tracking_decision(detection, stop_area)

            if action != last_action:
                command = apply_tracking_action(drive, action, speed, turn_speed)
                last_action = action
            else:
                command = None

            now = time.monotonic()
            if command is not None or now - last_report_at >= 1.0:
                area = 0 if detection is None else detection.area
                print(
                    f"color={color} action={action} reason={reason} area={area:.0f}",
                    flush=True,
                )
                last_report_at = now

            remaining = frame_interval - (time.monotonic() - frame_started_at)
            if remaining > 0:
                time.sleep(remaining)
    finally:
        drive.stop()


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

    print(f"backend={args.backend} tracking={args.color} Ctrl+C: stop")
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
