from __future__ import annotations

from typing import Any, Protocol

from buddy_ros.power_control import PowerState, power_state_from_status
from robot.power import RaspberryPiPowerMonitor, RaspberryPiPowerStatus


class PowerMonitor(Protocol):
    def read(self) -> RaspberryPiPowerStatus: ...


class MockPowerMonitor:
    def __init__(self, power_good: bool = True) -> None:
        self.power_good = power_good

    def read(self) -> RaspberryPiPowerStatus:
        return RaspberryPiPowerStatus(
            under_voltage=not self.power_good,
            under_voltage_occurred=False,
            raw=1 if not self.power_good else 0,
        )


def create_monitor(backend: str, *, mock_power_good: bool = True) -> PowerMonitor:
    if backend == "mock":
        return MockPowerMonitor(mock_power_good)
    if backend == "raspberry_pi":
        return RaspberryPiPowerMonitor()
    raise ValueError(f"Unsupported power backend: {backend}")


def create_power_node_class() -> type[Any]:
    """Create the node lazily so core tests do not require ROS 2."""
    try:
        from rclpy.node import Node
        from std_msgs.msg import Bool, String
    except ImportError as exc:
        raise RuntimeError(
            "ROS 2 Python packages are required. Source the Buddy ROS 2 "
            "environment before starting power_node."
        ) from exc

    class BuddyPowerNode(Node):
        def __init__(self) -> None:
            super().__init__("buddy_power")
            self.declare_parameter("backend", "mock")
            self.declare_parameter("mock_power_good", True)
            self.declare_parameter("publish_rate_hz", 1.0)

            backend = str(self.get_parameter("backend").value)
            publish_rate_hz = max(
                0.1,
                float(self.get_parameter("publish_rate_hz").value),
            )
            self.monitor = create_monitor(
                backend,
                mock_power_good=bool(
                    self.get_parameter("mock_power_good").value
                ),
            )
            self.power_publisher = self.create_publisher(
                Bool,
                "/safety/power_ok",
                10,
            )
            self.status_publisher = self.create_publisher(
                String,
                "/power/status",
                10,
            )
            self.last_status = ""
            self.timer = self.create_timer(1.0 / publish_rate_hz, self._publish)
            self.get_logger().info(
                f"power ready backend={backend} topic=/safety/power_ok "
                f"rate={publish_rate_hz:.1f}Hz"
            )

        def _publish(self) -> None:
            try:
                state = power_state_from_status(self.monitor.read())
            except RuntimeError as exc:
                state = PowerState(
                    power_ok=False,
                    under_voltage=False,
                    under_voltage_occurred=False,
                    raw=0,
                    error=str(exc),
                )

            power_message = Bool()
            power_message.data = state.power_ok
            self.power_publisher.publish(power_message)

            status = state.to_json()
            status_message = String()
            status_message.data = status
            self.status_publisher.publish(status_message)
            if status != self.last_status:
                log = (
                    self.get_logger().info
                    if state.power_ok
                    else self.get_logger().error
                )
                log(status)
                self.last_status = status

    return BuddyPowerNode


def main(args: list[str] | None = None) -> None:
    try:
        import rclpy
    except ImportError as exc:
        raise RuntimeError(
            "ROS 2 Python packages are required. Source the Buddy ROS 2 environment."
        ) from exc

    node_class = create_power_node_class()
    rclpy.init(args=args)
    node = node_class()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
