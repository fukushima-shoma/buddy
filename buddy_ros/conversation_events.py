from __future__ import annotations

import json
from typing import Any

from robot.conversation_state import ConversationEvent


class ConversationEventPublisher:
    """ROS adapter for transport-independent conversation events."""

    def __init__(self, node: Any, message_type: type[Any], qos_profile: Any) -> None:
        self._message_type = message_type
        self._event_publisher = node.create_publisher(
            message_type,
            "/conversation/event",
            qos_profile,
        )
        self._state_publisher = node.create_publisher(
            message_type,
            "/conversation/state",
            qos_profile,
        )
        self._reaction_publisher = node.create_publisher(
            message_type,
            "/conversation/reaction",
            qos_profile,
        )

    def publish(self, event: ConversationEvent) -> None:
        self._publish(self._state_publisher, event.phase.value)
        self._publish(self._reaction_publisher, event.reaction.value)
        self._publish(
            self._event_publisher,
            json.dumps(
                {
                    "phase": event.phase.value,
                    "reaction": event.reaction.value,
                    "reason": event.reason,
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
        )

    def _publish(self, publisher: Any, value: str) -> None:
        message = self._message_type()
        message.data = value
        publisher.publish(message)


class Ros2ConversationEventSink:
    """Own a small ROS node used by the non-ROS conversation process."""

    def __init__(self) -> None:
        try:
            import rclpy
            from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
            from std_msgs.msg import String
        except ImportError as exc:
            raise RuntimeError(
                "ROS 2 Python packages are required for conversation events."
            ) from exc

        self._rclpy = rclpy
        self._owns_context = not rclpy.ok()
        if self._owns_context:
            rclpy.init(args=[])
        self._node = rclpy.create_node("buddy_conversation_events")
        qos = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self._publisher = ConversationEventPublisher(self._node, String, qos)

    def __call__(self, event: ConversationEvent) -> None:
        if not self._rclpy.ok():
            return
        self._publisher.publish(event)
        self._rclpy.spin_once(self._node, timeout_sec=0.0)

    def close(self) -> None:
        self._node.destroy_node()
        if self._owns_context and self._rclpy.ok():
            self._rclpy.shutdown()
