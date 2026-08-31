from __future__ import annotations

import time
from typing import Any

from buddy_ros.odometry_control import PlanarPose, integrate_velocity, yaw_quaternion


def create_odometry_node_class() -> type[Any]:
    """Create the node lazily so core tests do not require ROS 2."""
    try:
        from geometry_msgs.msg import TransformStamped, Twist
        from nav_msgs.msg import Odometry
        from rclpy.node import Node
        from std_srvs.srv import Empty
        from tf2_ros import TransformBroadcaster
    except ImportError as exc:
        raise RuntimeError(
            "ROS 2 odometry packages are required. Source the Buddy ROS 2 "
            "environment before starting odometry_node."
        ) from exc

    class BuddyOdometryNode(Node):
        def __init__(self) -> None:
            super().__init__("buddy_odometry")
            self.declare_parameter("publish_rate_hz", 20.0)
            self.declare_parameter("command_timeout", 0.5)
            self.declare_parameter("frame_id", "odom")
            self.declare_parameter("child_frame_id", "base_footprint")

            publish_rate_hz = max(
                1.0,
                float(self.get_parameter("publish_rate_hz").value),
            )
            self.command_timeout = max(
                0.0,
                float(self.get_parameter("command_timeout").value),
            )
            self.frame_id = str(self.get_parameter("frame_id").value)
            self.child_frame_id = str(
                self.get_parameter("child_frame_id").value
            )
            self.pose = PlanarPose()
            self.linear_x = 0.0
            self.angular_z = 0.0
            self.last_command_at: float | None = None
            self.last_update_at = time.monotonic()

            self.publisher = self.create_publisher(Odometry, "/odom", 10)
            self.transform_broadcaster = TransformBroadcaster(self)
            self.subscription = self.create_subscription(
                Twist,
                "/cmd_vel",
                self._on_velocity,
                10,
            )
            self.reset_service = self.create_service(
                Empty,
                "/odom/reset",
                self._on_reset,
            )
            self.timer = self.create_timer(1.0 / publish_rate_hz, self._update)
            self.get_logger().info(
                "open-loop odometry ready topic=/odom "
                f"rate={publish_rate_hz:.1f}Hz"
            )

        def _on_velocity(self, message: Any) -> None:
            self.linear_x = float(message.linear.x)
            self.angular_z = float(message.angular.z)
            self.last_command_at = time.monotonic()

        def _on_reset(self, request: Any, response: Any) -> Any:
            del request
            self.pose = PlanarPose()
            self.linear_x = 0.0
            self.angular_z = 0.0
            self.last_command_at = None
            self.last_update_at = time.monotonic()
            self.get_logger().info("odometry reset")
            return response

        def _active_velocity(self, now: float) -> tuple[float, float]:
            if self.last_command_at is None:
                return (0.0, 0.0)
            if now - self.last_command_at > self.command_timeout:
                return (0.0, 0.0)
            return (self.linear_x, self.angular_z)

        def _update(self) -> None:
            now = time.monotonic()
            duration = max(0.0, now - self.last_update_at)
            self.last_update_at = now
            linear_x, angular_z = self._active_velocity(now)
            self.pose = integrate_velocity(
                self.pose,
                linear_x=linear_x,
                angular_z=angular_z,
                duration=duration,
            )
            self._publish(linear_x, angular_z)

        def _publish(self, linear_x: float, angular_z: float) -> None:
            stamp = self.get_clock().now().to_msg()
            quaternion = yaw_quaternion(self.pose.yaw)

            message = Odometry()
            message.header.stamp = stamp
            message.header.frame_id = self.frame_id
            message.child_frame_id = self.child_frame_id
            message.pose.pose.position.x = self.pose.x
            message.pose.pose.position.y = self.pose.y
            message.pose.pose.orientation.z = quaternion[2]
            message.pose.pose.orientation.w = quaternion[3]
            message.twist.twist.linear.x = linear_x
            message.twist.twist.angular.z = angular_z
            # Open-loop odometry is intentionally marked as uncertain.
            message.pose.covariance[0] = 0.25
            message.pose.covariance[7] = 0.25
            message.pose.covariance[35] = 0.5
            message.twist.covariance[0] = 0.25
            message.twist.covariance[7] = 0.25
            message.twist.covariance[35] = 0.5
            self.publisher.publish(message)

            transform = TransformStamped()
            transform.header.stamp = stamp
            transform.header.frame_id = self.frame_id
            transform.child_frame_id = self.child_frame_id
            transform.transform.translation.x = self.pose.x
            transform.transform.translation.y = self.pose.y
            transform.transform.rotation.z = quaternion[2]
            transform.transform.rotation.w = quaternion[3]
            self.transform_broadcaster.sendTransform(transform)

    return BuddyOdometryNode


def main(args: list[str] | None = None) -> None:
    try:
        import rclpy
    except ImportError as exc:
        raise RuntimeError(
            "ROS 2 Python packages are required. Source the ROS 2 environment."
        ) from exc

    node_class = create_odometry_node_class()
    rclpy.init(args=args)
    node = node_class()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
