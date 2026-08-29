from __future__ import annotations

from dataclasses import dataclass

from robot.motor import BuddyDrive, MotorCommand, _clamp


@dataclass(frozen=True)
class VelocityCommand:
    """ROS velocity command using metres/sec and radians/sec.

    Positive angular velocity means a left turn.
    """

    linear_x: float
    angular_z: float


class DifferentialDriveController:
    """Convert velocity commands into Buddy's signed wheel outputs."""

    def __init__(
        self,
        drive: BuddyDrive,
        *,
        max_linear_speed: float = 0.3,
        max_angular_speed: float = 1.5,
    ) -> None:
        if max_linear_speed <= 0 or max_angular_speed <= 0:
            raise ValueError("Maximum linear and angular speeds must be positive.")
        self.drive = drive
        self.max_linear_speed = max_linear_speed
        self.max_angular_speed = max_angular_speed

    def apply(self, velocity: VelocityCommand) -> MotorCommand:
        linear = _clamp(
            velocity.linear_x / self.max_linear_speed,
            -1.0,
            1.0,
        )
        angular = _clamp(
            velocity.angular_z / self.max_angular_speed,
            -1.0,
            1.0,
        )

        # BuddyDrive's left/right output labels follow the existing verified
        # wiring. Positive angular.z must therefore use the same polarity as
        # BuddyDrive.left().
        left = linear + angular
        right = linear - angular
        largest = max(1.0, abs(left), abs(right))
        left /= largest
        right /= largest
        return self.drive.wheels(
            left * self.drive.max_speed,
            right * self.drive.max_speed,
        )

    def stop(self) -> MotorCommand:
        return self.drive.stop()

    def close(self) -> None:
        self.drive.close()
