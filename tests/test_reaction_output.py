import unittest

from robot.reaction import ReactionCommand
from robot.reaction_output import (
    MockReactionDriver,
    ReactionOutputController,
    render_reaction,
)


class ReactionOutputTest(unittest.TestCase):
    def test_controller_applies_changes_and_suppresses_duplicates(self) -> None:
        driver = MockReactionDriver()
        controller = ReactionOutputController(driver)
        command = ReactionCommand("smile", "warm-white", "breathe", "none")

        self.assertTrue(controller.apply(command))
        self.assertFalse(controller.apply(command))
        self.assertEqual(driver.commands, [command])

    def test_terminal_renderer_exposes_face_and_all_output_channels(self) -> None:
        rendered = render_reaction(
            ReactionCommand("big-smile", "green", "sparkle", "success")
        )

        self.assertIn("(≧▽≦)", rendered)
        self.assertIn("light=green/sparkle", rendered)
        self.assertIn("sound=success", rendered)


if __name__ == "__main__":
    unittest.main()
