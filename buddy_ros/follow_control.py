from __future__ import annotations

from dataclasses import dataclass

from buddy_ros.person_control import PersonTarget


@dataclass(frozen=True)
class FollowCommand:
    action: str
    reason: str
    linear_x: float = 0.0
    angular_z: float = 0.0


def decide_follow_command(
    target: PersonTarget | None,
    distance_m: float | None,
    *,
    enabled: bool,
    obstacle_latched: bool,
    safety_stop_reason: str | None = None,
    linear_speed: float = 0.3,
    angular_speed: float = 1.5,
) -> FollowCommand:
    """Combine person and range inputs without touching motor hardware."""
    if not enabled:
        return FollowCommand("stop", "disabled")
    if safety_stop_reason is not None:
        return FollowCommand("stop", safety_stop_reason)
    if obstacle_latched:
        return FollowCommand("stop", "obstacle")
    if target is None:
        return FollowCommand("stop", "person-not-ready")
    if target.status == "confirming":
        return FollowCommand("stop", "person-confirming")
    if not target.detected or target.status != "detected":
        return FollowCommand("stop", "not-found")

    if distance_m is None:
        if target.position == "left":
            return FollowCommand(
                "left",
                "distance-not-ready-turning",
                angular_z=abs(angular_speed),
            )
        if target.position == "right":
            return FollowCommand(
                "right",
                "distance-not-ready-turning",
                angular_z=-abs(angular_speed),
            )
        return FollowCommand("stop", "distance-not-ready")

    if target.position == "left":
        return FollowCommand(
            "left",
            "tracking",
            angular_z=abs(angular_speed),
        )
    if target.position == "right":
        return FollowCommand(
            "right",
            "tracking",
            angular_z=-abs(angular_speed),
        )
    if target.position == "center":
        return FollowCommand(
            "forward",
            "tracking",
            linear_x=abs(linear_speed),
        )
    return FollowCommand("stop", "invalid-position")
