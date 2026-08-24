import unittest

from robot.interaction import (
    GpioButtonStartTrigger,
    KeyboardStartTrigger,
    run_interaction_station,
)


class SequenceTrigger:
    name = "mock"

    def __init__(self, values: list[bool]) -> None:
        self._values = iter(values)
        self.closed = False

    def wait(self) -> bool:
        return next(self._values)

    def close(self) -> None:
        self.closed = True


class FakeButton:
    def __init__(self) -> None:
        self.presses = 0
        self.releases = 0
        self.closed = False

    def wait_for_press(self) -> None:
        self.presses += 1

    def wait_for_release(self) -> None:
        self.releases += 1

    def close(self) -> None:
        self.closed = True


class InteractionTest(unittest.TestCase):
    def test_keyboard_enter_starts_and_q_stops(self) -> None:
        values = iter(["", "q"])
        trigger = KeyboardStartTrigger(lambda _: next(values))

        self.assertTrue(trigger.wait())
        self.assertFalse(trigger.wait())

    def test_gpio_button_waits_for_complete_press(self) -> None:
        button = FakeButton()
        trigger = GpioButtonStartTrigger(17, button=button)

        self.assertTrue(trigger.wait())
        trigger.close()

        self.assertEqual(button.presses, 1)
        self.assertEqual(button.releases, 1)
        self.assertTrue(button.closed)

    def test_station_transitions_and_resets_each_session(self) -> None:
        trigger = SequenceTrigger([True, True, False])
        logs: list[str] = []
        resets: list[str] = []

        completed = run_interaction_station(
            trigger=trigger,
            run_session=lambda: 4,
            reset_session=lambda: resets.append("reset"),
            output=logs.append,
        )

        self.assertEqual(completed, 2)
        self.assertEqual(resets, ["reset", "reset"])
        self.assertTrue(trigger.closed)
        self.assertIn("state=conversation session=1", logs)
        self.assertIn("state=waiting session=2 completed-turns=4", logs)
        self.assertEqual(logs[-1], "state=stopped")

    def test_session_limit_stops_without_an_extra_wait(self) -> None:
        trigger = SequenceTrigger([True])

        completed = run_interaction_station(
            trigger=trigger,
            run_session=lambda: 1,
            sessions=1,
            output=lambda _: None,
        )

        self.assertEqual(completed, 1)
        self.assertTrue(trigger.closed)

    def test_negative_session_limit_is_rejected(self) -> None:
        trigger = SequenceTrigger([])

        with self.assertRaisesRegex(ValueError, "sessions"):
            run_interaction_station(
                trigger=trigger,
                run_session=lambda: 1,
                sessions=-1,
            )


if __name__ == "__main__":
    unittest.main()
