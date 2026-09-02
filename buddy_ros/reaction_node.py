from __future__ import annotations

from typing import Any

from robot.reaction import conversation_event_from_json, reaction_command_for


class ReactionCoordinator:
    """Convert conversation events into semantic, hardware-free commands."""

    def __init__(self, node: Any, message_type: type[Any], qos_profile: Any) -> None:
        self._node = node
        self._message_type = message_type
        self._publisher = node.create_publisher(
            message_type,
            "/reaction/command",
            qos_profile,
        )
        self._subscription = node.create_subscription(
            message_type,
            "/conversation/event",
            self._on_event,
            qos_profile,
        )

    def _on_event(self, message: Any) -> None:
        try:
            command = reaction_command_for(conversation_event_from_json(message.data))
        except ValueError as exc:
            self._node.get_logger().warning(str(exc))
            return
        output = self._message_type()
        output.data = command.to_json()
        self._publisher.publish(output)


def main(args: list[str] | None = None) -> None:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    from std_msgs.msg import String

    rclpy.init(args=args)
    node = Node("buddy_reaction")
    qos = QoSProfile(
        depth=1,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
        reliability=ReliabilityPolicy.RELIABLE,
    )
    ReactionCoordinator(node, String, qos)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
