from __future__ import annotations

from typing import Any

from buddy_ros.distance_control import range_reading_from_cm
from robot.distance import DistanceSensor, MockDistanceSensor


def create_sensor(
    backend: str,
    *,
    mock_distance_cm: float = 100.0,
    distance_mode: int = 2,
    timing_budget_ms: int = 100,
) -> DistanceSensor:
    if backend == "mock":
        return MockDistanceSensor(mock_distance_cm)
    if backend == "vl53l1x":
        from robot.vl53l1x_driver import Vl53l1xDistanceSensor

        return Vl53l1xDistanceSensor(
            distance_mode=distance_mode,
            timing_budget_ms=timing_budget_ms,
        )
    raise ValueError(f"Unsupported distance backend: {backend}")


def create_distance_node_class() -> type[Any]:
    """Create the node lazily so core tests do not require ROS 2."""
    try:
        from rclpy.node import Node
        from sensor_msgs.msg import Range
    except ImportError as exc:
        raise RuntimeError(
            "ROS 2 Python packages are required. Source the ROS 2 environment "
            "before starting buddy_robot distance_node."
        ) from exc

    class BuddyDistanceNode(Node):
        def __init__(self) -> None:
            super().__init__("buddy_distance")
            self.declare_parameter("backend", "mock")
            self.declare_parameter("mock_distance_cm", 100.0)
            self.declare_parameter("distance_mode", 2)
            self.declare_parameter("timing_budget_ms", 100)
            self.declare_parameter("publish_rate_hz", 10.0)
            self.declare_parameter("frame_id", "front_distance_sensor")
            self.declare_parameter("field_of_view", 0.47)
            self.declare_parameter("min_range_m", 0.04)
            self.declare_parameter("max_range_m", 4.0)

            backend = str(self.get_parameter("backend").value)
            self.frame_id = str(self.get_parameter("frame_id").value)
            self.field_of_view = float(
                self.get_parameter("field_of_view").value
            )
            self.min_range_m = float(self.get_parameter("min_range_m").value)
            self.max_range_m = float(self.get_parameter("max_range_m").value)
            publish_rate_hz = max(
                0.1,
                float(self.get_parameter("publish_rate_hz").value),
            )
            self.sensor = create_sensor(
                backend,
                mock_distance_cm=float(
                    self.get_parameter("mock_distance_cm").value
                ),
                distance_mode=int(self.get_parameter("distance_mode").value),
                timing_budget_ms=int(
                    self.get_parameter("timing_budget_ms").value
                ),
            )
            self.sensor.start()
            self.publisher = self.create_publisher(Range, "/distance/front", 10)
            self.timer = self.create_timer(1.0 / publish_rate_hz, self._publish)
            self.get_logger().info(
                f"distance ready backend={backend} topic=/distance/front "
                f"rate={publish_rate_hz:.1f}Hz"
            )

        def _publish(self) -> None:
            reading = range_reading_from_cm(
                self.sensor.read_distance_cm(),
                min_range_m=self.min_range_m,
                max_range_m=self.max_range_m,
            )
            if reading is None:
                return

            message = Range()
            message.header.stamp = self.get_clock().now().to_msg()
            message.header.frame_id = self.frame_id
            message.radiation_type = Range.INFRARED
            message.field_of_view = self.field_of_view
            message.min_range = reading.min_range_m
            message.max_range = reading.max_range_m
            message.range = reading.range_m
            self.publisher.publish(message)

        def destroy_node(self) -> None:
            self.sensor.close()
            super().destroy_node()

    return BuddyDistanceNode


def main(args: list[str] | None = None) -> None:
    try:
        import rclpy
    except ImportError as exc:
        raise RuntimeError(
            "ROS 2 Python packages are required. Source the ROS 2 environment."
        ) from exc

    node_class = create_distance_node_class()
    rclpy.init(args=args)
    node = node_class()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
