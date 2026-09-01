from __future__ import annotations

import json
from math import isfinite
import time
from typing import Any

from buddy_ros.follow_control import FollowCommand, FollowCoordinator
from buddy_ros.person_control import PersonTarget


def create_follow_node_class() -> type[Any]:
    """Create the node lazily so core tests do not require ROS 2."""
    try:
        from geometry_msgs.msg import Twist
        from rclpy.node import Node
        from sensor_msgs.msg import Range
        from std_msgs.msg import Bool, String
        from std_srvs.srv import SetBool
    except ImportError as exc:
        raise RuntimeError(
            "ROS 2 Python packages are required. Source the Buddy ROS 2 "
            "environment before starting follow_node."
        ) from exc

    class BuddyFollowNode(Node):
        def __init__(self) -> None:
            super().__init__("buddy_follow")
            self.declare_parameter("enabled", False)
            self.declare_parameter("update_rate_hz", 10.0)
            self.declare_parameter("input_timeout", 0.75)
            self.declare_parameter("stop_distance_m", 0.6)
            self.declare_parameter("resume_distance_m", 0.7)
            self.declare_parameter("resume_confirm_frames", 5)
            self.declare_parameter("linear_speed", 0.3)
            self.declare_parameter("angular_speed", 1.5)
            self.declare_parameter("require_power_status", False)
            self.declare_parameter("power_timeout", 2.5)

            enabled = bool(self.get_parameter("enabled").value)
            input_timeout = max(
                0.1,
                float(self.get_parameter("input_timeout").value),
            )
            linear_speed = max(
                0.0,
                float(self.get_parameter("linear_speed").value),
            )
            angular_speed = max(
                0.0,
                float(self.get_parameter("angular_speed").value),
            )
            require_power_status = bool(
                self.get_parameter("require_power_status").value
            )
            power_timeout = max(
                0.1,
                float(self.get_parameter("power_timeout").value),
            )
            update_rate_hz = max(
                0.1,
                float(self.get_parameter("update_rate_hz").value),
            )
            self.coordinator = FollowCoordinator(
                input_timeout=input_timeout,
                stop_distance_m=(
                    float(self.get_parameter("stop_distance_m").value)
                ),
                resume_distance_m=(
                    float(self.get_parameter("resume_distance_m").value)
                ),
                resume_confirm_frames=int(
                    self.get_parameter("resume_confirm_frames").value
                ),
                linear_speed=linear_speed,
                angular_speed=angular_speed,
                require_power_status=require_power_status,
                power_timeout=power_timeout,
            )
            self.coordinator.enabled = enabled
            self.last_status = ""

            self.command_publisher = self.create_publisher(Twist, "/cmd_vel", 10)
            self.status_publisher = self.create_publisher(
                String,
                "/follow/status",
                10,
            )
            self.person_subscription = self.create_subscription(
                String,
                "/person/target",
                self._on_person,
                10,
            )
            self.distance_subscription = self.create_subscription(
                Range,
                "/distance/front",
                self._on_distance,
                10,
            )
            self.power_subscription = self.create_subscription(
                Bool,
                "/safety/power_ok",
                self._on_power,
                10,
            )
            self.enable_service = self.create_service(
                SetBool,
                "/follow/enable",
                self._on_enable,
            )
            self.timer = self.create_timer(1.0 / update_rate_hz, self._update)
            self.get_logger().info(
                "follow ready enabled="
                f"{str(self.coordinator.enabled).lower()} service=/follow/enable"
            )

        def _on_person(self, message: Any) -> None:
            try:
                target = PersonTarget.from_json(message.data)
            except ValueError as exc:
                self.get_logger().warning(f"invalid person target: {exc}")
                return
            self.coordinator.update_target(target, measured_at=time.monotonic())

        def _on_distance(self, message: Any) -> None:
            distance_m = float(message.range)
            if not isfinite(distance_m) or distance_m < 0:
                return
            self.coordinator.update_distance(
                distance_m,
                measured_at=time.monotonic(),
            )

        def _on_power(self, message: Any) -> None:
            self.coordinator.update_power(
                bool(message.data),
                measured_at=time.monotonic(),
            )

        def _on_enable(self, request: Any, response: Any) -> Any:
            command = self.coordinator.set_enabled(bool(request.data))
            if not self.coordinator.enabled:
                self._publish_command(command)
            response.success = True
            response.message = (
                "person following enabled"
                if self.coordinator.enabled
                else "stopped"
            )
            return response

        def _update(self) -> None:
            now = time.monotonic()
            command = self.coordinator.command(now=now)
            self._publish_command(command)

        def _publish_command(self, command: FollowCommand) -> None:
            message = Twist()
            message.linear.x = command.linear_x
            message.angular.z = command.angular_z
            self.command_publisher.publish(message)

            status = json.dumps(
                {
                    "action": command.action,
                    "enabled": self.coordinator.enabled,
                    "reason": command.reason,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            status_message = String()
            status_message.data = status
            self.status_publisher.publish(status_message)
            if status != self.last_status:
                self.get_logger().info(status)
                self.last_status = status

        def destroy_node(self) -> None:
            self._publish_command(FollowCommand("stop", "shutdown"))
            super().destroy_node()

    return BuddyFollowNode


def main(args: list[str] | None = None) -> None:
    try:
        import rclpy
    except ImportError as exc:
        raise RuntimeError(
            "ROS 2 Python packages are required. Source the Buddy ROS 2 environment."
        ) from exc

    node_class = create_follow_node_class()
    rclpy.init(args=args)
    node = node_class()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
