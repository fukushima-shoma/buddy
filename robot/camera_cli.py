from __future__ import annotations

import argparse
from pathlib import Path

from robot.camera import CameraDevice, MockCamera, capture_still


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture a still image with Buddy.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("captures/latest.jpg"),
        help="Output image path. Default: captures/latest.jpg.",
    )
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--warmup", type=float, default=2.0)
    parser.add_argument(
        "--backend",
        choices=("mock", "picamera2"),
        default="mock",
    )
    return parser


def create_camera(backend: str, width: int, height: int) -> CameraDevice:
    if backend == "mock":
        return MockCamera()
    if backend == "picamera2":
        from robot.picamera2_driver import Picamera2Device

        return Picamera2Device(width=width, height=height)
    raise ValueError(f"Unsupported camera backend: {backend}")


def main() -> int:
    args = build_parser().parse_args()
    camera = create_camera(args.backend, args.width, args.height)
    output = capture_still(camera, args.output, warmup=args.warmup)
    print(f"captured={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
