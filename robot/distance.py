from __future__ import annotations

from typing import Protocol


class DistanceSensor(Protocol):
    def start(self) -> None:
        """Start continuous distance measurements."""

    def read_distance_cm(self) -> float | None:
        """Return the latest distance in centimeters, or None if not ready."""

    def close(self) -> None:
        """Stop measurements and release resources."""


def obstacle_detected(distance_cm: float | None, stop_distance_cm: float) -> bool:
    if distance_cm is None:
        return False
    return distance_cm <= max(0.0, stop_distance_cm)


class MockDistanceSensor:
    def __init__(self, distance_cm: float = 100.0) -> None:
        self.distance_cm = distance_cm
        self.started = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def read_distance_cm(self) -> float:
        return self.distance_cm

    def close(self) -> None:
        self.closed = True
