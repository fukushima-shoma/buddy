from __future__ import annotations

import unittest
from array import array
import subprocess

from robot.interaction import (
    GpioButtonStartTrigger,
    KeyboardStartTrigger,
    PorcupineWakeWordTrigger,
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


class FakeWakeWordEngine:
    frame_length = 4
    sample_rate = 16000

    def __init__(self) -> None:
        self.calls = 0
        self.deleted = False

    def process(self, samples: list[int]) -> int:
        if len(samples) != self.frame_length:
            raise AssertionError("unexpected frame length")
        self.calls += 1
        return 0 if self.calls == 2 else -1

    def delete(self) -> None:
        self.deleted = True


class FakeAudioProcess:
    class Stdout:
        def __init__(self, chunks: list[bytes]) -> None:
            self.chunks = list(chunks)

        def read(self, size: int) -> bytes:
            chunk = self.chunks.pop(0)
            if len(chunk) != size:
                raise AssertionError("unexpected audio frame size")
            return chunk

    def __init__(self, chunks: list[bytes]) -> None:
        self.stdout = self.Stdout(chunks)
        self.running = True
        self.terminated = False

    def poll(self) -> int | None:
        return None if self.running else 0

    def terminate(self) -> None:
        self.running = False
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        self.running = False
        return 0

    def kill(self) -> None:
        self.running = False


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

    def test_wake_word_reads_alsa_frames_until_detected(self) -> None:
        engine = FakeWakeWordEngine()
        frame = array("h", [1, 2, 3, 4]).tobytes()
        process = FakeAudioProcess([frame, frame])
        commands: list[list[str]] = []

        def factory(command: list[str], **kwargs: object) -> FakeAudioProcess:
            commands.append(command)
            self.assertEqual(kwargs["stdout"], subprocess.PIPE)
            return process

        trigger = PorcupineWakeWordTrigger(
            device="plughw:2,0",
            engine=engine,
            process_factory=factory,
        )

        self.assertTrue(trigger.wait())
        trigger.close()

        self.assertEqual(engine.calls, 2)
        self.assertTrue(engine.deleted)
        self.assertTrue(process.terminated)
        self.assertEqual(
            commands[0][0:4],
            ["arecord", "--quiet", "-D", "plughw:2,0"],
        )
        self.assertIn("16000", commands[0])

    def test_wake_word_sensitivity_range_is_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "sensitivity"):
            PorcupineWakeWordTrigger(
                engine=FakeWakeWordEngine(),
                sensitivity=1.1,
            )

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
