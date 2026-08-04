from __future__ import annotations

import argparse
from pathlib import Path

from robot.color_detection import HSV_RANGES, detect_largest_color


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect a colored object in an image.")
    parser.add_argument("--input", type=Path, default=Path("captures/latest.jpg"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("captures/color-detected.jpg"),
    )
    parser.add_argument("--color", choices=tuple(HSV_RANGES), default="red")
    parser.add_argument("--min-area", type=float, default=1000.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    detection = detect_largest_color(
        args.input,
        args.output,
        args.color,
        min_area=args.min_area,
    )

    if detection is None:
        print(f"detected=false color={args.color} output={args.output}")
    else:
        print(
            f"detected=true color={detection.color} "
            f"position={detection.position} "
            f"center=({detection.center_x},{detection.center_y}) "
            f"area={detection.area:.0f} output={args.output}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
