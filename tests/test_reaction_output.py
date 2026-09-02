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

    def test_high_priority_reaction_interrupts_immediately(self) -> None:
        now = [0.0]
        driver = MockReactionDriver()
        controller = ReactionOutputController(driver, clock=lambda: now[0])
        smile = ReactionCommand(
            "smile", "warm-white", "breathe", "none", 20, 1000
        )
        alert = ReactionCommand("alert", "red", "blink", "warning", 100, 1200)

        controller.apply(smile)
        now[0] = 0.1

        self.assertTrue(controller.apply(alert))
        self.assertEqual(driver.commands, [smile, alert])

    def test_low_priority_reaction_waits_for_minimum_duration(self) -> None:
        now = [0.0]
        driver = MockReactionDriver()
        controller = ReactionOutputController(driver, clock=lambda: now[0])
        alert = ReactionCommand("alert", "red", "blink", "warning", 100, 1200)
        smile = ReactionCommand(
            "smile", "warm-white", "breathe", "none", 20, 600
        )

        controller.apply(alert)
        now[0] = 0.2
        self.assertFalse(controller.apply(smile))
        self.assertEqual(controller.pending, smile)
        now[0] = 1.19
        self.assertFalse(controller.tick())
        now[0] = 1.2
        self.assertTrue(controller.tick())
        self.assertEqual(driver.commands, [alert, smile])

    def test_terminal_renderer_exposes_face_and_all_output_channels(self) -> None:
        rendered = render_reaction(
            ReactionCommand("big-smile", "green", "sparkle", "success")
        )

        self.assertIn("(≧▽≦)", rendered)
        self.assertIn("light=green/sparkle", rendered)
        self.assertIn("sound=success", rendered)
        self.assertIn("priority=0 hold_ms=0", rendered)


if __name__ == "__main__":
    unittest.main()
