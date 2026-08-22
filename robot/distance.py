from __future__ import annotations

from statistics import median
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


def retain_recent_distance(
    measured_distance_cm: float | None,
    previous_distance_cm: float | None,
    previous_measurement_at: float | None,
    now: float,
    stale_after: float = 0.5,
) -> tuple[float | None, float | None]:
    """Keep the latest valid reading between sensor measurement cycles."""
    if measured_distance_cm is not None:
        return measured_distance_cm, now
    if (
        previous_distance_cm is not None
        and previous_measurement_at is not None
        and now - previous_measurement_at <= stale_after
    ):
        return previous_distance_cm, previous_measurement_at
    return None, previous_measurement_at


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


def update_distance_median(
    measured_distance_cm: float | None,
    recent_distances_cm: tuple[float, ...],
    window_size: int = 3,
) -> tuple[float | None, tuple[float, ...]]:
    """Filter isolated distance spikes with a short rolling median."""
    if measured_distance_cm is None:
        return None, recent_distances_cm
    window_size = max(1, window_size)
    updated = (*recent_distances_cm, float(measured_distance_cm))[-window_size:]
    return float(median(updated)), updated


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
