from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, sin


@dataclass(frozen=True)
class PlanarPose:
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0


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


def yaw_quaternion(yaw: float) -> tuple[float, float, float, float]:
    return (0.0, 0.0, sin(yaw / 2.0), cos(yaw / 2.0))
