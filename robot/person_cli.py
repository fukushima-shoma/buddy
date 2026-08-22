from __future__ import annotations

import argparse
from pathlib import Path
import time

from robot.person_detection import (
    HogPersonDetector,
    PersonDetection,
    save_annotated_image,
)
from robot.picamera2_driver import Picamera2FrameSource


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect a person without moving Buddy's motors."
    )
    parser.add_argument("--duration", type=float, default=15.0)
    parser.add_argument("--fps", type=float, default=2.0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--min-confidence", type=float, default=0.2)
    parser.add_argument("--scale", type=float, default=1.05)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("captures/person-detected.jpg"),
    )
    return parser


def detection_status(detection: PersonDetection | None) -> str:
    if detection is None:
        return "not-found"
    return detection.position


def main() -> int:
    args = build_parser().parse_args()
    detector = HogPersonDetector(
        min_confidence=args.min_confidence,
        scale=args.scale,
    )
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
            detection, last_annotated = detector.detect(frame)
            status = detection_status(detection)
            now = time.monotonic()
            if status != last_status or now - last_report_at >= 1.0:
                if detection is None:
                    print("person=not-found", flush=True)
                else:
                    print(
                        f"person=detected position={detection.position} "
                        f"center=({detection.center_x},{detection.center_y}) "
                        f"confidence={detection.confidence:.2f}",
                        flush=True,
                    )
                last_status = status
                last_report_at = now

            remaining = frame_interval - (time.monotonic() - frame_started_at)
            if remaining > 0:
                time.sleep(remaining)
    except KeyboardInterrupt:
        print("Stopping person detection.")
    finally:
        source.close()

    if last_annotated is not None:
        save_annotated_image(args.output, last_annotated)
        print(f"snapshot={args.output.expanduser()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
