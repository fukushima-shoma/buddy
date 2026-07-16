from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


MIN_SPEED = 0.0
MAX_SPEED = 1.0


class MotorDriver(Protocol):
    """Backend interface for motor output."""

    def set_left(self, speed: float) -> None:
        """Set left motor speed from -1.0 to 1.0."""

    def set_right(self, speed: float) -> None:
        """Set right motor speed from -1.0 to 1.0."""

    def stop(self) -> None:
        """Stop both motors."""

    def close(self) -> None:
        """Release backend resources."""


@dataclass(frozen=True)
class MotorCommand:
    left: float
    right: float


class BuddyDrive:
    """High-level 2WD drive controller."""

    def __init__(self, driver: MotorDriver, max_speed: float = 0.35) -> None:
        self.driver = driver
        self.max_speed = _clamp(max_speed, MIN_SPEED, MAX_SPEED)

    def forward(self, speed: float | None = None) -> MotorCommand:
        value = self._speed(speed)
        return self._apply(value, value)

    def back(self, speed: float | None = None) -> MotorCommand:
        value = self._speed(speed)
        return self._apply(-value, -value)

    def left(self, speed: float | None = None) -> MotorCommand:
        value = self._speed(speed)
        return self._apply(-value, value)

    def right(self, speed: float | None = None) -> MotorCommand:
        value = self._speed(speed)
        return self._apply(value, -value)

    def stop(self) -> MotorCommand:
        self.driver.stop()
        return MotorCommand(0.0, 0.0)

    def close(self) -> None:
        self.driver.close()

    def _speed(self, speed: float | None) -> float:
        if speed is None:
            return self.max_speed
        return _clamp(speed, MIN_SPEED, self.max_speed)

    def _apply(self, left: float, right: float) -> MotorCommand:
        command = MotorCommand(left, right)
        self.driver.set_left(command.left)
        self.driver.set_right(command.right)
        return command


class MockMotorDriver:
    """Motor backend for development without Raspberry Pi GPIO."""

    def __init__(self) -> None:
        self.left_speed = 0.0
        self.right_speed = 0.0
        self.events: list[str] = []

    def set_left(self, speed: float) -> None:
        self.left_speed = _clamp(speed, -MAX_SPEED, MAX_SPEED)
        self.events.append(f"left={self.left_speed:.2f}")

    def set_right(self, speed: float) -> None:
        self.right_speed = _clamp(speed, -MAX_SPEED, MAX_SPEED)
        self.events.append(f"right={self.right_speed:.2f}")

    def stop(self) -> None:
        self.left_speed = 0.0
        self.right_speed = 0.0
        self.events.append("stop")

    def close(self) -> None:
        self.events.append("close")


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
