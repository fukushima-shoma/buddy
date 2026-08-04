from __future__ import annotations

import argparse
from pathlib import Path
import time

from robot.color_detection import (
    HSV_RANGES,
    ColorDetection,
    detect_color_frame,
)
from robot.picamera2_driver import Picamera2FrameSource


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Continuously detect a colored object with Buddy's camera."
    )
    parser.add_argument("--color", choices=tuple(HSV_RANGES), default="red")
    parser.add_argument("--duration", type=float, default=15.0)
    parser.add_argument("--fps", type=float, default=5.0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--min-area", type=float, default=1000.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("captures/live-color.jpg"),
    )
    return parser


def detection_status(detection: ColorDetection | None) -> str:
    if detection is None:
        return "not-found"
    return detection.position


def main() -> int:
    args = build_parser().parse_args()
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV is required. Install it with: "
            "sudo apt install -y python3-opencv opencv-data"
        ) from exc

    source = Picamera2FrameSource(width=args.width, height=args.height)
    started_at = time.monotonic()
    last_report_at = 0.0
    last_status = ""
    last_annotated = None
    frame_interval = 1.0 / max(0.1, args.fps)

    source.start()
    try:
        while args.duration <= 0 or time.monotonic() - started_at < args.duration:
            frame_started_at = time.monotonic()
            frame = source.capture_array()
            detection, last_annotated = detect_color_frame(
                frame,
                args.color,
                min_area=args.min_area,
            )
            status = detection_status(detection)
            now = time.monotonic()
            if status != last_status or now - last_report_at >= 1.0:
                if detection is None:
                    print(f"color={args.color} position=not-found", flush=True)
                else:
                    print(
                        f"color={detection.color} position={detection.position} "
                        f"center=({detection.center_x},{detection.center_y}) "
                        f"area={detection.area:.0f}",
                        flush=True,
                    )
                last_status = status
                last_report_at = now

            remaining = frame_interval - (time.monotonic() - frame_started_at)
            if remaining > 0:
                time.sleep(remaining)
    except KeyboardInterrupt:
        print("Stopping color detection.")
    finally:
        source.close()

    if last_annotated is not None:
        output = args.output.expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(output), last_annotated):
            raise RuntimeError(f"Could not write image: {output}")
        print(f"snapshot={output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
