from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class RangeReading:
    """ROS-compatible distance values expressed in metres."""

    range_m: float
    min_range_m: float
    max_range_m: float


def range_reading_from_cm(
    distance_cm: float | None,
    *,
    min_range_m: float = 0.04,
    max_range_m: float = 4.0,
) -> RangeReading | None:
    """Convert the existing centimetre reading to a ROS range reading."""
    if distance_cm is None or not isfinite(distance_cm) or distance_cm < 0:
        return None
    if min_range_m < 0 or max_range_m <= min_range_m:
        raise ValueError("Range limits must satisfy 0 <= min < max.")
    return RangeReading(
        range_m=distance_cm / 100.0,
        min_range_m=min_range_m,
        max_range_m=max_range_m,
    )
