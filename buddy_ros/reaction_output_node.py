from __future__ import annotations

from typing import Any, Callable

from robot.reaction import ReactionCommand
from robot.reaction_output import ReactionOutputController, render_reaction


class LoggingReactionDriver:
    """Mock output driver that renders reactions through the ROS logger."""

    def __init__(self, output: Callable[[str], None]) -> None:
        self._output = output

    def apply(self, command: ReactionCommand) -> None:
        self._output(render_reaction(command))


class ReactionOutputSubscriber:
    def __init__(
        self,
        node: Any,
        message_type: type[Any],
        qos_profile: Any,
        controller: ReactionOutputController,
    ) -> None:
        self._node = node
        self._controller = controller
        self._subscription = node.create_subscription(
            message_type,
            "/reaction/command",
            self._on_command,
            qos_profile,
        )

    def _on_command(self, message: Any) -> None:
        try:
            command = ReactionCommand.from_json(message.data)
        except ValueError as exc:
            self._node.get_logger().warning(str(exc))
            return
        self._controller.apply(command)


def main(args: list[str] | None = None) -> None:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    from std_msgs.msg import String

    rclpy.init(args=args)
    node = Node("buddy_reaction_output")
    qos = QoSProfile(
        depth=1,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
        reliability=ReliabilityPolicy.RELIABLE,
    )
    driver = LoggingReactionDriver(node.get_logger().info)
    controller = ReactionOutputController(driver)
    ReactionOutputSubscriber(node, String, qos, controller)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
