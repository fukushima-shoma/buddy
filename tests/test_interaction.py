from __future__ import annotations

import unittest
import subprocess

from robot.interaction import (
    GpioButtonStartTrigger,
    InteractionState,
    KeyboardStartTrigger,
    TriggerActivation,
    VoskWakeWordTrigger,
    is_active_hour,
    normalize_wake_phrase,
    run_interaction_station,
    wake_phrase_detected,
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


class FakeWakeWordRecognizer:
    def __init__(self) -> None:
        self.calls = 0
        self.reset_calls = 0

    def Reset(self) -> None:
        self.calls = 0
        self.reset_calls += 1

    def AcceptWaveform(self, chunk: bytes) -> bool:
        if len(chunk) != 3200:
            raise AssertionError("unexpected audio frame size")
        self.calls += 1
        return self.calls == 2

    def PartialResult(self) -> str:
        return '{"partial": "ねえ バディ"}'

    def Result(self) -> str:
        return '{"text": "ねえ バディ"}'


class SilentWakeWordRecognizer(FakeWakeWordRecognizer):
    def AcceptWaveform(self, chunk: bytes) -> bool:
        if len(chunk) != 3200:
            raise AssertionError("unexpected audio frame size")
        self.calls += 1
        return False


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
    def test_active_hours_support_daytime_and_overnight_windows(self) -> None:
        self.assertTrue(is_active_hour(9, 8, 20))
        self.assertFalse(is_active_hour(22, 8, 20))
        self.assertTrue(is_active_hour(23, 20, 8))
        self.assertTrue(is_active_hour(7, 20, 8))
        self.assertFalse(is_active_hour(12, 20, 8))

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
        recognizer = FakeWakeWordRecognizer()
        frame = bytes(3200)
        process = FakeAudioProcess([frame, frame])
        commands: list[list[str]] = []

        def factory(command: list[str], **kwargs: object) -> FakeAudioProcess:
            commands.append(command)
            self.assertEqual(kwargs["stdout"], subprocess.PIPE)
            return process

        trigger = VoskWakeWordTrigger(
            device="plughw:2,0",
            recognizer=recognizer,
            process_factory=factory,
        )

        self.assertTrue(trigger.wait())
        trigger.close()

        self.assertEqual(recognizer.calls, 2)
        self.assertEqual(recognizer.reset_calls, 1)
        self.assertTrue(process.terminated)
        self.assertEqual(
            commands[0][0:4],
            ["arecord", "--quiet", "-D", "plughw:2,0"],
        )
        self.assertIn("16000", commands[0])

    def test_wake_word_does_not_accept_a_partial_result(self) -> None:
        recognizer = FakeWakeWordRecognizer()
        frame = bytes(3200)
        process = FakeAudioProcess([frame, frame])
        trigger = VoskWakeWordTrigger(
            recognizer=recognizer,
            process_factory=lambda *args, **kwargs: process,
        )

        self.assertTrue(trigger.wait())

        self.assertEqual(recognizer.calls, 2)

    def test_wake_word_resets_recognizer_before_every_wait(self) -> None:
        recognizer = FakeWakeWordRecognizer()
        frame = bytes(3200)
        processes = [
            FakeAudioProcess([frame, frame]),
            FakeAudioProcess([frame, frame]),
        ]

        def factory(command: list[str], **kwargs: object) -> FakeAudioProcess:
            return processes.pop(0)

        trigger = VoskWakeWordTrigger(
            recognizer=recognizer,
            process_factory=factory,
        )

        self.assertTrue(trigger.wait())
        self.assertTrue(trigger.wait())

        self.assertEqual(recognizer.reset_calls, 2)
        self.assertEqual(processes, [])

    def test_wake_word_can_start_a_proactive_session_after_idle_time(self) -> None:
        recognizer = FakeWakeWordRecognizer()
        frame = bytes(3200)
        process = FakeAudioProcess([frame])
        trigger = VoskWakeWordTrigger(
            recognizer=recognizer,
            proactive_interval=0.1,
            chunk_duration=0.1,
            process_factory=lambda *args, **kwargs: process,
        )

        self.assertTrue(trigger.wait())
        self.assertEqual(trigger.activation, TriggerActivation.PROACTIVE)
        self.assertTrue(process.terminated)

    def test_proactive_session_respects_allowed_hours(self) -> None:
        recognizer = SilentWakeWordRecognizer()
        frame = bytes(3200)
        process = FakeAudioProcess([frame, frame])
        allowed = iter((False, True))
        trigger = VoskWakeWordTrigger(
            recognizer=recognizer,
            proactive_interval=0.1,
            chunk_duration=0.1,
            proactive_allowed=lambda: next(allowed),
            process_factory=lambda *args, **kwargs: process,
        )

        self.assertTrue(trigger.wait())
        self.assertEqual(trigger.activation, TriggerActivation.PROACTIVE)

    def test_wake_word_takes_priority_over_proactive_timeout(self) -> None:
        recognizer = FakeWakeWordRecognizer()
        frame = bytes(3200)
        process = FakeAudioProcess([frame, frame])
        trigger = VoskWakeWordTrigger(
            recognizer=recognizer,
            proactive_interval=0.2,
            chunk_duration=0.1,
            process_factory=lambda *args, **kwargs: process,
        )

        self.assertTrue(trigger.wait())
        self.assertEqual(trigger.activation, TriggerActivation.USER)

    def test_wake_word_phrase_must_not_be_empty(self) -> None:
        with self.assertRaisesRegex(ValueError, "phrase"):
            VoskWakeWordTrigger(
                recognizer=FakeWakeWordRecognizer(),
                phrase="  ",
            )

    def test_wake_word_payload_ignores_spacing_and_punctuation(self) -> None:
        targets = (normalize_wake_phrase("ねえ バディ"),)

        self.assertTrue(
            wake_phrase_detected('{"partial": "ねえ、バディ！"}', targets)
        )
        self.assertFalse(
            wake_phrase_detected('{"partial": "今日は遊ぼう"}', targets)
        )
        self.assertFalse(
            wake_phrase_detected(
                '{"partial": "ねえバディって言ってみた"}',
                targets,
            )
        )
        self.assertFalse(
            wake_phrase_detected('{"text": "バイバイ"}', targets)
        )
        self.assertFalse(wake_phrase_detected("not-json", targets))
        self.assertFalse(wake_phrase_detected("[]", targets))

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

    def test_station_reports_typed_state_changes(self) -> None:
        trigger = SequenceTrigger([True])
        states: list[InteractionState] = []

        run_interaction_station(
            trigger=trigger,
            run_session=lambda: 1,
            sessions=1,
            on_state_change=states.append,
            output=lambda _: None,
        )

        self.assertEqual(
            states,
            [
                InteractionState.WAITING,
                InteractionState.CONVERSATION,
                InteractionState.STOPPED,
            ],
        )

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

    def test_station_delays_rearming_after_a_completed_session(self) -> None:
        trigger = SequenceTrigger([True, False])
        delays: list[float] = []
        logs: list[str] = []

        completed = run_interaction_station(
            trigger=trigger,
            run_session=lambda: 1,
            rearm_delay=1.5,
            output=logs.append,
            sleeper=delays.append,
        )

        self.assertEqual(completed, 1)
        self.assertEqual(delays, [1.5])
        self.assertIn("state=cooldown duration=1.5s", logs)

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
