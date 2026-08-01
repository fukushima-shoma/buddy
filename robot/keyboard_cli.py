from __future__ import annotations

import argparse
from collections.abc import Callable, Iterator
from contextlib import contextmanager
import select
import sys
import termios
import tty

from robot.motor import BuddyDrive, MotorCommand
from robot.motor_cli import create_driver


KEY_COMMANDS = {
    "w": "forward",
    "s": "back",
    "a": "left",
    "d": "right",
    " ": "stop",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Drive Buddy with W/A/S/D keys.")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--max-speed", type=float, default=1.0)
    parser.add_argument("--left-scale", type=float, default=0.95)
    parser.add_argument("--right-scale", type=float, default=1.0)
    parser.add_argument(
        "--deadman-timeout",
        type=float,
        default=0.5,
        help="Stop when no movement key repeats for this many seconds.",
    )
    parser.add_argument(
        "--backend",
        choices=("mock", "gpiozero"),
        default="mock",
    )
    return parser


def command_for_key(key: str) -> str | None:
    return KEY_COMMANDS.get(key.lower())


def run_keyboard_control(
    drive: BuddyDrive,
    read_key: Callable[[float], str | None],
    speed: float,
    deadman_timeout: float,
) -> None:
    moving = False

    try:
        while True:
            key = read_key(deadman_timeout)
            if key is None:
                if moving:
                    _print_command("stop", drive.stop())
                    moving = False
                continue

            if key.lower() == "q":
                break

            action = command_for_key(key)
            if action is None:
                continue

            if action == "stop":
                command = drive.stop()
                moving = False
            else:
                command = getattr(drive, action)(speed)
                moving = True
            _print_command(action, command)
    finally:
        drive.stop()


def read_terminal_key(timeout: float) -> str | None:
    ready, _, _ = select.select([sys.stdin], [], [], max(0.0, timeout))
    if not ready:
        return None
    return sys.stdin.read(1)


@contextmanager
def cbreak_terminal() -> Iterator[None]:
    if not sys.stdin.isatty():
        raise RuntimeError("Keyboard control requires an interactive terminal.")

    descriptor = sys.stdin.fileno()
    previous = termios.tcgetattr(descriptor)
    try:
        tty.setcbreak(descriptor)
        yield
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)


def _print_command(action: str, command: MotorCommand) -> None:
    print(
        f"command={action} left={command.left:.2f} right={command.right:.2f}",
        flush=True,
    )


def main() -> int:
    args = build_parser().parse_args()
    driver = create_driver(args.backend)
    drive = BuddyDrive(
        driver,
        max_speed=args.max_speed,
        left_scale=args.left_scale,
        right_scale=args.right_scale,
    )

    print("W: forward  A: left  S: back  D: right  Space: stop  Q: quit")
    try:
        with cbreak_terminal():
            run_keyboard_control(
                drive,
                read_terminal_key,
                args.speed,
                args.deadman_timeout,
            )
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        drive.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
