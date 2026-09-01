from __future__ import annotations

from dataclasses import dataclass

from buddy_ros.person_control import PersonTarget
from robot.distance import ObstacleLatch


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


class FollowCoordinator:
    """Own follow input freshness and safety state without requiring ROS 2."""

    def __init__(
        self,
        *,
        input_timeout: float = 0.75,
        stop_distance_m: float = 0.6,
        resume_distance_m: float = 0.7,
        resume_confirm_frames: int = 5,
        linear_speed: float = 0.3,
        angular_speed: float = 1.5,
        require_power_status: bool = False,
        power_timeout: float = 2.5,
    ) -> None:
        if input_timeout <= 0 or power_timeout <= 0:
            raise ValueError("timeouts must be greater than 0")
        if linear_speed < 0 or angular_speed < 0:
            raise ValueError("speeds must be 0 or greater")
        self.input_timeout = input_timeout
        self.linear_speed = linear_speed
        self.angular_speed = angular_speed
        self.require_power_status = require_power_status
        self.power_timeout = power_timeout
        self.enabled = False
        self.obstacle_latch = ObstacleLatch(
            stop_distance_cm=stop_distance_m * 100.0,
            resume_distance_cm=resume_distance_m * 100.0,
            resume_confirm_frames=resume_confirm_frames,
        )
        self.latest_target: PersonTarget | None = None
        self.latest_target_at: float | None = None
        self.latest_distance_m: float | None = None
        self.latest_distance_at: float | None = None
        self.latest_power_good: bool | None = None
        self.latest_power_at: float | None = None

    def set_enabled(self, enabled: bool) -> FollowCommand:
        self.enabled = enabled
        return (
            self.command(now=None)
            if enabled
            else FollowCommand("stop", "disabled")
        )

    def update_target(self, target: PersonTarget, *, measured_at: float) -> None:
        self.latest_target = target
        self.latest_target_at = measured_at

    def update_distance(self, distance_m: float, *, measured_at: float) -> None:
        self.latest_distance_m = distance_m
        self.latest_distance_at = measured_at
        distance_cm = distance_m * 100.0
        self.obstacle_latch.update(distance_cm, raw_distance_cm=distance_cm)

    def update_power(self, power_good: bool, *, measured_at: float) -> None:
        self.latest_power_good = power_good
        self.latest_power_at = measured_at

    def _fresh(
        self,
        value: object,
        measured_at: float | None,
        now: float,
    ) -> object | None:
        if measured_at is None or now - measured_at > self.input_timeout:
            return None
        return value

    def _power_stop_reason(self, now: float) -> str | None:
        if not self.require_power_status:
            return None
        if (
            self.latest_power_at is None
            or now - self.latest_power_at > self.power_timeout
        ):
            return "power-not-ready"
        if self.latest_power_good is not True:
            return "power-low"
        return None

    def command(self, *, now: float | None) -> FollowCommand:
        if now is None:
            target = None
            distance_m = None
            safety_stop_reason = (
                "power-not-ready" if self.require_power_status else None
            )
        else:
            target = self._fresh(self.latest_target, self.latest_target_at, now)
            distance_m = self._fresh(
                self.latest_distance_m,
                self.latest_distance_at,
                now,
            )
            safety_stop_reason = self._power_stop_reason(now)
        return decide_follow_command(
            target if isinstance(target, PersonTarget) else None,
            float(distance_m) if distance_m is not None else None,
            enabled=self.enabled,
            obstacle_latched=self.obstacle_latch.latched,
            safety_stop_reason=safety_stop_reason,
            linear_speed=self.linear_speed,
            angular_speed=self.angular_speed,
        )
