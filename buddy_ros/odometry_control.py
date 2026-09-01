from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, isfinite, pi, sin


@dataclass(frozen=True)
class PlanarPose:
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0


@dataclass(frozen=True)
class DifferentialDriveGeometry:
    """Physical values needed to turn encoder ticks into wheel travel."""

    wheel_diameter_m: float
    wheel_separation_m: float
    ticks_per_revolution: int

    def __post_init__(self) -> None:
        values = (self.wheel_diameter_m, self.wheel_separation_m)
        if not all(isfinite(value) and value > 0 for value in values):
            raise ValueError("wheel dimensions must be finite and greater than 0")
        if self.ticks_per_revolution <= 0:
            raise ValueError("ticks_per_revolution must be greater than 0")

    @property
    def meters_per_tick(self) -> float:
        return pi * self.wheel_diameter_m / self.ticks_per_revolution

    def tick_distances(
        self,
        left_delta: int,
        right_delta: int,
    ) -> tuple[float, float]:
        return (
            left_delta * self.meters_per_tick,
            right_delta * self.meters_per_tick,
        )


def normalize_angle(angle: float) -> float:
    return atan2(sin(angle), cos(angle))


def integrate_velocity(
    pose: PlanarPose,
    *,
    linear_x: float,
    angular_z: float,
    duration: float,
) -> PlanarPose:
    """Integrate a planar velocity command using an exact circular arc."""
    if duration < 0:
        raise ValueError("duration must be 0 or greater")
    if duration == 0:
        return pose

    next_yaw = pose.yaw + angular_z * duration
    if abs(angular_z) < 1e-9:
        x = pose.x + linear_x * cos(pose.yaw) * duration
        y = pose.y + linear_x * sin(pose.yaw) * duration
    else:
        radius = linear_x / angular_z
        x = pose.x + radius * (sin(next_yaw) - sin(pose.yaw))
        y = pose.y - radius * (cos(next_yaw) - cos(pose.yaw))
    return PlanarPose(x=x, y=y, yaw=normalize_angle(next_yaw))


def integrate_wheel_distances(
    pose: PlanarPose,
    *,
    left_distance: float,
    right_distance: float,
    wheel_separation: float,
) -> PlanarPose:
    """Integrate measured differential-drive wheel travel."""
    if not isfinite(wheel_separation) or wheel_separation <= 0:
        raise ValueError("wheel_separation must be finite and greater than 0")
    if not all(isfinite(value) for value in (left_distance, right_distance)):
        raise ValueError("wheel distances must be finite")

    center_distance = (left_distance + right_distance) / 2.0
    yaw_delta = (right_distance - left_distance) / wheel_separation
    if abs(yaw_delta) < 1e-9:
        x = pose.x + center_distance * cos(pose.yaw)
        y = pose.y + center_distance * sin(pose.yaw)
    else:
        next_yaw = pose.yaw + yaw_delta
        radius = center_distance / yaw_delta
        x = pose.x + radius * (sin(next_yaw) - sin(pose.yaw))
        y = pose.y - radius * (cos(next_yaw) - cos(pose.yaw))
    return PlanarPose(x=x, y=y, yaw=normalize_angle(pose.yaw + yaw_delta))


class EncoderOdometry:
    """Track cumulative encoder ticks without depending on GPIO or ROS 2."""

    def __init__(
        self,
        geometry: DifferentialDriveGeometry,
        *,
        max_tick_delta: int | None = None,
    ) -> None:
        if max_tick_delta is not None and max_tick_delta <= 0:
            raise ValueError("max_tick_delta must be greater than 0")
        self.geometry = geometry
        self.max_tick_delta = max_tick_delta
        self.pose = PlanarPose()
        self._last_ticks: tuple[int, int] | None = None
        self._last_timestamp: float | None = None

    def reset(self, pose: PlanarPose = PlanarPose()) -> None:
        self.pose = pose
        self._last_ticks = None
        self._last_timestamp = None

    def update(
        self,
        left_ticks: int,
        right_ticks: int,
        *,
        timestamp: float,
    ) -> PlanarPose:
        if not isfinite(timestamp):
            raise ValueError("timestamp must be finite")
        if self._last_timestamp is not None and timestamp <= self._last_timestamp:
            raise ValueError("timestamp must increase")

        previous = self._last_ticks
        if previous is None:
            self._last_ticks = (left_ticks, right_ticks)
            self._last_timestamp = timestamp
            return self.pose

        deltas = (left_ticks - previous[0], right_ticks - previous[1])
        if self.max_tick_delta is not None and any(
            abs(delta) > self.max_tick_delta for delta in deltas
        ):
            raise ValueError("encoder tick delta exceeds configured limit")

        left_distance, right_distance = self.geometry.tick_distances(*deltas)
        self.pose = integrate_wheel_distances(
            self.pose,
            left_distance=left_distance,
            right_distance=right_distance,
            wheel_separation=self.geometry.wheel_separation_m,
        )
        self._last_ticks = (left_ticks, right_ticks)
        self._last_timestamp = timestamp
        return self.pose


def yaw_quaternion(yaw: float) -> tuple[float, float, float, float]:
    return (0.0, 0.0, sin(yaw / 2.0), cos(yaw / 2.0))
