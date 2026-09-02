import json
import unittest

from buddy_ros.reaction_node import ReactionCoordinator


class FakeMessage:
    def __init__(self, data: str = "") -> None:
        self.data = data


class FakePublisher:
    def __init__(self) -> None:
        self.messages: list[FakeMessage] = []

    def publish(self, message: FakeMessage) -> None:
        self.messages.append(message)


class FakeLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, message: str) -> None:
        self.warnings.append(message)


class FakeNode:
    def __init__(self) -> None:
        self.publisher = FakePublisher()
        self.callback = None
        self.logger = FakeLogger()

    def create_publisher(self, *args: object) -> FakePublisher:
        return self.publisher

    def create_subscription(self, *args: object) -> object:
        self.callback = args[2]
        return object()

    def get_logger(self) -> FakeLogger:
        return self.logger


class RosReactionNodeTest(unittest.TestCase):
    def test_conversation_event_publishes_one_atomic_reaction_command(self) -> None:
        node = FakeNode()
        ReactionCoordinator(node, FakeMessage, object())

        node.callback(
            FakeMessage(
                '{"phase":"speaking","reaction":"cautious",'
                '"reason":"power-low"}'
            )
        )

        self.assertEqual(len(node.publisher.messages), 1)
        self.assertEqual(
            json.loads(node.publisher.messages[0].data),
            {
                "expression": "alert",
                "light_animation": "blink",
                "light_color": "red",
                "minimum_duration_ms": 1200,
                "priority": 100,
                "sound_cue": "warning",
            },
        )

    def test_invalid_event_is_logged_and_ignored(self) -> None:
        node = FakeNode()
        ReactionCoordinator(node, FakeMessage, object())

        node.callback(FakeMessage("not-json"))

        self.assertEqual(node.publisher.messages, [])
        self.assertEqual(node.logger.warnings, ["Invalid conversation event payload."])


if __name__ == "__main__":
    unittest.main()
