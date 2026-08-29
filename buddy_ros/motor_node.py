from __future__ import annotations

from typing import Any

from buddy_ros.motor_control import DifferentialDriveController, VelocityCommand
from robot.motor import BuddyDrive, MockMotorDriver, MotorDriver


def create_driver(backend: str) -> MotorDriver:
    if backend == "mock":
        return MockMotorDriver()
    if backend == "gpiozero":
        from robot.gpiozero_driver import Tb6612GpioDriver

        return Tb6612GpioDriver()
    raise ValueError(f"Unsupported motor backend: {backend}")


def create_motor_node_class() -> type[Any]:
    """Create the node class lazily so core tests do not require ROS 2."""
    try:
        import rclpy
        from geometry_msgs.msg import Twist
        from rclpy.node import Node
    except ImportError as exc:
        raise RuntimeError(
            "ROS 2 Python packages are required. Source the ROS 2 environment "
            "before starting buddy_robot motor_node."
        ) from exc

    class BuddyMotorNode(Node):
        def __init__(self) -> None:
            super().__init__("buddy_motor")
            self.declare_parameter("backend", "mock")
            self.declare_parameter("max_speed", 0.35)
            self.declare_parameter("max_linear_speed", 0.3)
            self.declare_parameter("max_angular_speed", 1.5)
            self.declare_parameter("left_scale", 1.0)
            self.declare_parameter("right_scale", 1.0)

            backend = str(self.get_parameter("backend").value)
            drive = BuddyDrive(
                create_driver(backend),
                max_speed=float(self.get_parameter("max_speed").value),
                left_scale=float(self.get_parameter("left_scale").value),
                right_scale=float(self.get_parameter("right_scale").value),
            )
            self.controller = DifferentialDriveController(
                drive,
                max_linear_speed=float(
                    self.get_parameter("max_linear_speed").value
                ),
                max_angular_speed=float(
                    self.get_parameter("max_angular_speed").value
                ),
            )
            self.subscription = self.create_subscription(
                Twist,
                "/cmd_vel",
                self._on_velocity,
                10,
            )
            self.get_logger().info(
                f"motor ready backend={backend} max-speed={drive.max_speed:.2f}"
            )

        def _on_velocity(self, message: Any) -> None:
            command = self.controller.apply(
                VelocityCommand(
                    linear_x=float(message.linear.x),
                    angular_z=float(message.angular.z),
                )
            )
            self.get_logger().info(
                f"cmd_vel left={command.left:.2f} right={command.right:.2f}"
            )

        def destroy_node(self) -> None:
            self.controller.stop()
            self.controller.close()
            super().destroy_node()

    return BuddyMotorNode


def main(args: list[str] | None = None) -> None:
    try:
        import rclpy
    except ImportError as exc:
        raise RuntimeError(
            "ROS 2 Python packages are required. Source the ROS 2 environment."
        ) from exc

    node_class = create_motor_node_class()
    rclpy.init(args=args)
    node = node_class()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
