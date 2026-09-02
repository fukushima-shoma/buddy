import unittest

from buddy_ros.reaction_output_node import ReactionOutputSubscriber
from robot.reaction_output import MockReactionDriver, ReactionOutputController


class FakeMessage:
    def __init__(self, data: str = "") -> None:
        self.data = data


class FakeLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, message: str) -> None:
        self.warnings.append(message)


class FakeNode:
    def __init__(self) -> None:
        self.callback = None
        self.timer_callback = None
        self.logger = FakeLogger()

    def create_subscription(self, *args: object) -> object:
        self.callback = args[2]
        return object()

    def get_logger(self) -> FakeLogger:
        return self.logger

    def create_timer(self, period: float, callback: object) -> object:
        self.timer_callback = callback
        return object()


class RosReactionOutputNodeTest(unittest.TestCase):
    def test_valid_command_reaches_driver(self) -> None:
        node = FakeNode()
        driver = MockReactionDriver()
        ReactionOutputSubscriber(
            node,
            FakeMessage,
            object(),
            ReactionOutputController(driver),
        )

        node.callback(
            FakeMessage(
                '{"expression":"smile","light_color":"warm-white",'
                '"light_animation":"breathe","sound_cue":"none"}'
            )
        )

        self.assertEqual(driver.commands[0].expression, "smile")

    def test_invalid_command_is_logged_and_ignored(self) -> None:
        node = FakeNode()
        driver = MockReactionDriver()
        ReactionOutputSubscriber(
            node,
            FakeMessage,
            object(),
            ReactionOutputController(driver),
        )

        node.callback(FakeMessage("invalid"))

        self.assertEqual(driver.commands, [])
        self.assertEqual(node.logger.warnings, ["Invalid reaction command payload."])


if __name__ == "__main__":
    unittest.main()
