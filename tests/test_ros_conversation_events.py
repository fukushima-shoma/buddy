import json
import unittest

from buddy_ros.conversation_events import ConversationEventPublisher
from robot.conversation_state import (
    ConversationEvent,
    ConversationPhase,
    ConversationReaction,
)


class FakeMessage:
    def __init__(self) -> None:
        self.data = ""


class FakePublisher:
    def __init__(self) -> None:
        self.messages: list[FakeMessage] = []

    def publish(self, message: FakeMessage) -> None:
        self.messages.append(message)


class FakeNode:
    def __init__(self) -> None:
        self.publishers: dict[str, FakePublisher] = {}

    def create_publisher(
        self,
        message_type: type[FakeMessage],
        topic: str,
        qos_profile: object,
    ) -> FakePublisher:
        publisher = FakePublisher()
        self.publishers[topic] = publisher
        return publisher


class RosConversationEventsTest(unittest.TestCase):
    def test_adapter_publishes_state_reaction_and_atomic_event(self) -> None:
        node = FakeNode()
        publisher = ConversationEventPublisher(node, FakeMessage, object())

        publisher.publish(
            ConversationEvent(
                ConversationPhase.LISTENING,
                ConversationReaction.CALM,
                "awaiting-speech",
            )
        )

        self.assertEqual(
            node.publishers["/conversation/state"].messages[0].data,
            "listening",
        )
        self.assertEqual(
            node.publishers["/conversation/reaction"].messages[0].data,
            "calm",
        )
        self.assertEqual(
            json.loads(node.publishers["/conversation/event"].messages[0].data),
            {
                "phase": "listening",
                "reaction": "calm",
                "reason": "awaiting-speech",
            },
        )
