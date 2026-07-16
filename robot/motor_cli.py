from __future__ import annotations

import argparse
import time

from robot.motor import BuddyDrive, MockMotorDriver, MotorDriver


COMMANDS = ("forward", "back", "left", "right", "stop")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Control Buddy's 2WD motors.")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument(
        "--speed",
        type=float,
        default=None,
        help="Motor speed from 0.0 to 1.0. Limited by --max-speed.",
    )
    parser.add_argument(
        "--max-speed",
        type=float,
        default=0.35,
        help="Safety speed limit. Default: 0.35.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.5,
        help="Seconds to run before stopping. Ignored for stop. Default: 0.5.",
    )
    parser.add_argument(
        "--backend",
        choices=("mock", "gpiozero"),
        default="mock",
        help="Motor backend. Use gpiozero only after wiring is checked.",
    )
    return parser


def create_driver(backend: str) -> MotorDriver:
    if backend == "mock":
        return MockMotorDriver()
    if backend == "gpiozero":
        from robot.gpiozero_driver import Tb6612GpioDriver

        return Tb6612GpioDriver()
    raise ValueError(f"Unsupported backend: {backend}")


def main() -> int:
    args = build_parser().parse_args()
    driver = create_driver(args.backend)
    drive = BuddyDrive(driver, max_speed=args.max_speed)

    try:
        if args.command == "stop":
            command = drive.stop()
        else:
            command = getattr(drive, args.command)(args.speed)
        print(f"command={args.command} left={command.left:.2f} right={command.right:.2f}")

        if args.command != "stop":
            time.sleep(max(0.0, args.duration))
            drive.stop()
            print("command=stop left=0.00 right=0.00")
    finally:
        drive.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
