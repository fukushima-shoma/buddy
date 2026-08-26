from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from robot.audio import MockAudioPlayer, MockAudioRecorder, NoSpeechDetectedError
from robot.child_games import ChildGameController
from robot.conversation import MockReplyGenerator
from robot.conversation_loop_cli import (
    CHILD_RETRY_REPLIES,
    DEFAULT_FAREWELL_REPLY,
    DEFAULT_INACTIVITY_REPLY,
    MOBILITY_START_REPLY,
    MOBILITY_STOP_REPLY,
    MOBILITY_ALREADY_STOPPED_REPLY,
    MOBILITY_FAREWELL_REPLY,
    POWER_GOOD_REPLY,
    POWER_LOW_REPLY,
    build_parser,
    is_farewell_transcript,
    is_mobility_start_transcript,
    is_mobility_stop_transcript,
    run_conversation_loop,
)
from robot.speech import MockSpeechSynthesizer
from robot.transcription import MockTranscriber, is_unreliable_child_transcript


class InterruptingRecorder(MockAudioRecorder):
    def __init__(self) -> None:
        self.calls = 0

    def record(
        self,
        output: Path,
        *,
        duration: float,
        sample_rate: int,
    ) -> Path:
        self.calls += 1
        if self.calls > 1:
            raise KeyboardInterrupt
        return super().record(
            output,
            duration=duration,
            sample_rate=sample_rate,
        )


class NoSpeechRecorder(MockAudioRecorder):
    def record(
        self,
        output: Path,
        *,
        duration: float,
        sample_rate: int,
    ) -> Path:
        raise NoSpeechDetectedError("no speech")


class ConversationLoopTest(unittest.TestCase):
    def test_farewell_detection_ignores_spacing_and_punctuation(self) -> None:
        self.assertTrue(is_farewell_transcript("バイバイ！"))
        self.assertTrue(is_farewell_transcript("お話、おしまい。"))
        self.assertTrue(is_farewell_transcript("じゃあ、バイバイ"))
        self.assertFalse(is_farewell_transcript("バイバイって言って"))

    def test_mobility_commands_require_an_exact_phrase(self) -> None:
        self.assertTrue(is_mobility_start_transcript("ついてきて！"))
        self.assertTrue(is_mobility_stop_transcript("止まって。"))
        self.assertTrue(is_mobility_stop_transcript("ストップ"))
        self.assertFalse(is_mobility_start_transcript("ついてきてって言った"))
        self.assertFalse(is_mobility_stop_transcript("止まっているね"))

    def test_defaults_are_finite_and_do_not_use_hardware_or_api(self) -> None:
        args = build_parser().parse_args([])

        self.assertEqual(args.turns, 1)
        self.assertEqual(args.max_silence_turns, 2)
        self.assertEqual(args.audio_backend, "mock")
        self.assertEqual(args.transcription_backend, "mock")
        self.assertEqual(args.reply_backend, "mock")
        self.assertFalse(args.child_mode)
        self.assertEqual(args.memory, "none")
        self.assertEqual(args.memory_turns, 30)
        self.assertEqual(args.profile_memory, Path("data/buddy-memory.json"))
        self.assertFalse(args.auto_conversation_memory)
        self.assertEqual(
            args.conversation_memory_file,
            Path("data/conversation-memory.json"),
        )
        self.assertEqual(args.speech_backend, "mock")
        self.assertEqual(args.speech_style, "calm")
        self.assertEqual(args.playback_backend, "mock")
        self.assertEqual(args.start_trigger, "immediate")
        self.assertEqual(args.button_pin, 17)
        self.assertEqual(args.sessions, 0)
        self.assertIsNone(args.wake_word_model)
        self.assertEqual(args.wake_phrase, "ねえ バディ")
        self.assertIsNone(args.wake_word_device)
        self.assertEqual(args.orientation_backend, "off")
        self.assertEqual(args.mobility_backend, "off")
        self.assertEqual(args.power_monitor, "off")
        self.assertFalse(args.child_games)

    def test_two_turns_run_complete_pipeline_and_pause_once(self) -> None:
        with TemporaryDirectory() as directory:
            logs: list[str] = []
            pauses: list[float] = []
            reply_generator = MockReplyGenerator("返事")
            synthesizer = MockSpeechSynthesizer()
            player = MockAudioPlayer()

            completed = run_conversation_loop(
                recorder=MockAudioRecorder(),
                transcriber=MockTranscriber("質問"),
                reply_generator=reply_generator,
                synthesizer=synthesizer,
                player=player,
                input_path=Path(directory) / "input.wav",
                speech_output=Path(directory) / "reply.wav",
                duration=0.1,
                sample_rate=16000,
                language="ja",
                turns=2,
                pause=0.25,
                output=logs.append,
                sleeper=pauses.append,
            )

            self.assertEqual(completed, 2)
            self.assertEqual(reply_generator.inputs, ["質問", "質問"])
            self.assertEqual(synthesizer.inputs, ["返事", "返事"])
            self.assertEqual(len(player.played), 2)
            self.assertEqual(pauses, [0.25])
            self.assertIn("turn=2 reply=返事", logs)

    def test_successful_exchange_is_sent_to_persistent_memory_callback(self) -> None:
        exchanges: list[tuple[str, str]] = []

        completed = run_conversation_loop(
            recorder=MockAudioRecorder(),
            transcriber=MockTranscriber("青が好き"),
            reply_generator=MockReplyGenerator("青、きれいだね"),
            synthesizer=MockSpeechSynthesizer(),
            player=MockAudioPlayer(),
            input_path=Path("input.wav"),
            speech_output=Path("reply.wav"),
            duration=0.1,
            sample_rate=16000,
            language="ja",
            turns=1,
            pause=0,
            on_exchange=lambda user, assistant: exchanges.append((user, assistant)),
            output=lambda _: None,
        )

        self.assertEqual(completed, 1)
        self.assertEqual(exchanges, [("青が好き", "青、きれいだね")])

    def test_empty_transcript_skips_reply_speech_and_playback(self) -> None:
        with TemporaryDirectory() as directory:
            logs: list[str] = []
            reply_generator = MockReplyGenerator()
            synthesizer = MockSpeechSynthesizer()
            player = MockAudioPlayer()

            completed = run_conversation_loop(
                recorder=MockAudioRecorder(),
                transcriber=MockTranscriber(""),
                reply_generator=reply_generator,
                synthesizer=synthesizer,
                player=player,
                input_path=Path(directory) / "input.wav",
                speech_output=Path(directory) / "reply.wav",
                duration=0.1,
                sample_rate=16000,
                language="ja",
                turns=1,
                pause=0,
                output=logs.append,
                sleeper=lambda _: None,
            )

            self.assertEqual(completed, 1)
            self.assertEqual(reply_generator.inputs, [])
            self.assertEqual(synthesizer.inputs, [])
            self.assertEqual(player.played, [])
            self.assertIn("turn=1 reply=skipped reason=empty-transcript", logs)

    def test_ctrl_c_stops_unlimited_loop_cleanly(self) -> None:
        with TemporaryDirectory() as directory:
            logs: list[str] = []

            completed = run_conversation_loop(
                recorder=InterruptingRecorder(),
                transcriber=MockTranscriber("質問"),
                reply_generator=MockReplyGenerator("返事"),
                synthesizer=MockSpeechSynthesizer(),
                player=MockAudioPlayer(),
                input_path=Path(directory) / "input.wav",
                speech_output=Path(directory) / "reply.wav",
                duration=0.1,
                sample_rate=16000,
                language="ja",
                turns=0,
                pause=0,
                output=logs.append,
                sleeper=lambda _: None,
            )

            self.assertEqual(completed, 1)
            self.assertEqual(logs[-1], "Stopping conversation loop.")

    def test_farewell_ends_session_and_plays_goodbye_without_reply_api(self) -> None:
        with TemporaryDirectory() as directory:
            logs: list[str] = []
            reply_generator = MockReplyGenerator("呼ばれない")
            synthesizer = MockSpeechSynthesizer()
            player = MockAudioPlayer()
            stops: list[str] = []

            completed = run_conversation_loop(
                recorder=MockAudioRecorder(),
                transcriber=MockTranscriber("バイバイ。"),
                reply_generator=reply_generator,
                synthesizer=synthesizer,
                player=player,
                input_path=Path(directory) / "input.wav",
                speech_output=Path(directory) / "reply.wav",
                duration=0.1,
                sample_rate=16000,
                language="ja",
                turns=4,
                pause=0,
                stop_mobility=lambda: stops.append("stop") or True,
                output=logs.append,
                sleeper=lambda _: None,
            )

            self.assertEqual(completed, 1)
            self.assertEqual(reply_generator.inputs, [])
            self.assertEqual(synthesizer.inputs, [DEFAULT_FAREWELL_REPLY])
            self.assertEqual(len(player.played), 1)
            self.assertEqual(stops, ["stop"])
            self.assertIn("reason=conversation-ended", logs[-3])

    def test_spoken_start_command_starts_person_follow_without_reply_api(self) -> None:
        starts: list[str] = []
        reply_generator = MockReplyGenerator("呼ばれない")
        synthesizer = MockSpeechSynthesizer()

        completed = run_conversation_loop(
            recorder=MockAudioRecorder(),
            transcriber=MockTranscriber("ついてきて"),
            reply_generator=reply_generator,
            synthesizer=synthesizer,
            player=MockAudioPlayer(),
            input_path=Path("input.wav"),
            speech_output=Path("reply.wav"),
            duration=0.1,
            sample_rate=16000,
            language="ja",
            turns=1,
            pause=0,
            start_mobility=lambda: starts.append("start") or True,
            output=lambda _: None,
        )

        self.assertEqual(completed, 1)
        self.assertEqual(starts, ["start"])
        self.assertEqual(reply_generator.inputs, [])
        self.assertEqual(synthesizer.inputs, [MOBILITY_START_REPLY])

    def test_spoken_stop_command_stops_before_acknowledgement(self) -> None:
        events: list[str] = []

        class OrderedSynthesizer(MockSpeechSynthesizer):
            def synthesize(self, text: str, output: Path) -> Path:
                events.append("reply")
                return super().synthesize(text, output)

        synthesizer = OrderedSynthesizer()
        completed = run_conversation_loop(
            recorder=MockAudioRecorder(),
            transcriber=MockTranscriber("止まって"),
            reply_generator=MockReplyGenerator("呼ばれない"),
            synthesizer=synthesizer,
            player=MockAudioPlayer(),
            input_path=Path("input.wav"),
            speech_output=Path("reply.wav"),
            duration=0.1,
            sample_rate=16000,
            language="ja",
            turns=1,
            pause=0,
            stop_mobility=lambda: events.append("stop") or True,
            output=lambda _: None,
        )

        self.assertEqual(completed, 1)
        self.assertEqual(events, ["stop", "reply"])
        self.assertEqual(synthesizer.inputs, [MOBILITY_STOP_REPLY])

    def test_stop_command_reports_when_robot_was_already_stopped(self) -> None:
        synthesizer = MockSpeechSynthesizer()

        run_conversation_loop(
            recorder=MockAudioRecorder(),
            transcriber=MockTranscriber("ストップ"),
            reply_generator=MockReplyGenerator("呼ばれない"),
            synthesizer=synthesizer,
            player=MockAudioPlayer(),
            input_path=Path("input.wav"),
            speech_output=Path("reply.wav"),
            duration=0.1,
            sample_rate=16000,
            language="ja",
            turns=1,
            pause=0,
            stop_mobility=lambda: False,
            output=lambda _: None,
        )

        self.assertEqual(synthesizer.inputs, [MOBILITY_ALREADY_STOPPED_REPLY])

    def test_farewell_announces_stop_when_person_follow_was_running(self) -> None:
        synthesizer = MockSpeechSynthesizer()
        stops: list[str] = []

        run_conversation_loop(
            recorder=MockAudioRecorder(),
            transcriber=MockTranscriber("バイバイ"),
            reply_generator=MockReplyGenerator("呼ばれない"),
            synthesizer=synthesizer,
            player=MockAudioPlayer(),
            input_path=Path("input.wav"),
            speech_output=Path("reply.wav"),
            duration=0.1,
            sample_rate=16000,
            language="ja",
            turns=1,
            pause=0,
            stop_mobility=lambda: stops.append("stop") or True,
            mobility_active=lambda: True,
            output=lambda _: None,
        )

        self.assertEqual(stops, ["stop"])
        self.assertEqual(synthesizer.inputs, [MOBILITY_FAREWELL_REPLY])

    def test_silence_does_not_end_session_while_person_follow_is_running(self) -> None:
        logs: list[str] = []
        synthesizer = MockSpeechSynthesizer()

        completed = run_conversation_loop(
            recorder=NoSpeechRecorder(),
            transcriber=MockTranscriber("呼ばれない"),
            reply_generator=MockReplyGenerator(),
            synthesizer=synthesizer,
            player=MockAudioPlayer(),
            input_path=Path("input.wav"),
            speech_output=Path("reply.wav"),
            duration=0.1,
            sample_rate=16000,
            language="ja",
            turns=2,
            pause=0,
            retry_replies=CHILD_RETRY_REPLIES,
            mobility_active=lambda: True,
            output=logs.append,
        )

        self.assertEqual(completed, 2)
        self.assertEqual(synthesizer.inputs, [])
        self.assertEqual(
            sum("mobility=running reason=no-speech" in log for log in logs),
            2,
        )

    def test_reply_interruption_stop_word_stops_mobility_and_confirms(self) -> None:
        class StopRequestPlayer(MockAudioPlayer):
            def __init__(self) -> None:
                super().__init__()
                self.requested = True

            def consume_stop_request(self) -> bool:
                requested = self.requested
                self.requested = False
                return requested

        stops: list[str] = []
        synthesizer = MockSpeechSynthesizer()

        run_conversation_loop(
            recorder=MockAudioRecorder(),
            transcriber=MockTranscriber("こんにちは"),
            reply_generator=MockReplyGenerator("こんにちは"),
            synthesizer=synthesizer,
            player=StopRequestPlayer(),
            input_path=Path("input.wav"),
            speech_output=Path("reply.wav"),
            duration=0.1,
            sample_rate=16000,
            language="ja",
            turns=1,
            pause=0,
            stop_mobility=lambda: stops.append("stop") or True,
            output=lambda _: None,
        )

        self.assertEqual(stops, ["stop"])
        self.assertEqual(synthesizer.inputs, ["こんにちは", MOBILITY_STOP_REPLY])

    def test_low_power_blocks_person_follow_start(self) -> None:
        starts: list[str] = []
        synthesizer = MockSpeechSynthesizer()

        run_conversation_loop(
            recorder=MockAudioRecorder(),
            transcriber=MockTranscriber("ついてきて"),
            reply_generator=MockReplyGenerator("呼ばれない"),
            synthesizer=synthesizer,
            player=MockAudioPlayer(),
            input_path=Path("input.wav"),
            speech_output=Path("reply.wav"),
            duration=0.1,
            sample_rate=16000,
            language="ja",
            turns=1,
            pause=0,
            start_mobility=lambda: starts.append("start") or True,
            power_good=lambda: False,
            output=lambda _: None,
        )

        self.assertEqual(starts, [])
        self.assertEqual(synthesizer.inputs, [POWER_LOW_REPLY])

    def test_low_power_stops_running_person_follow_before_recording(self) -> None:
        stops: list[str] = []
        synthesizer = MockSpeechSynthesizer()

        run_conversation_loop(
            recorder=MockAudioRecorder(),
            transcriber=MockTranscriber("呼ばれない"),
            reply_generator=MockReplyGenerator(),
            synthesizer=synthesizer,
            player=MockAudioPlayer(),
            input_path=Path("input.wav"),
            speech_output=Path("reply.wav"),
            duration=0.1,
            sample_rate=16000,
            language="ja",
            turns=1,
            pause=0,
            stop_mobility=lambda: stops.append("stop") or True,
            mobility_active=lambda: True,
            power_good=lambda: False,
            output=lambda _: None,
        )

        self.assertEqual(stops, ["stop"])
        self.assertEqual(synthesizer.inputs, [POWER_LOW_REPLY])

    def test_power_status_question_is_answered_without_reply_api(self) -> None:
        reply_generator = MockReplyGenerator("呼ばれない")
        synthesizer = MockSpeechSynthesizer()

        run_conversation_loop(
            recorder=MockAudioRecorder(),
            transcriber=MockTranscriber("電池は大丈夫？"),
            reply_generator=reply_generator,
            synthesizer=synthesizer,
            player=MockAudioPlayer(),
            input_path=Path("input.wav"),
            speech_output=Path("reply.wav"),
            duration=0.1,
            sample_rate=16000,
            language="ja",
            turns=1,
            pause=0,
            power_good=lambda: True,
            output=lambda _: None,
        )

        self.assertEqual(reply_generator.inputs, [])
        self.assertEqual(synthesizer.inputs, [POWER_GOOD_REPLY])

    def test_active_child_game_uses_oshimai_without_ending_conversation(self) -> None:
        game = ChildGameController()
        game.handle("どうぶつクイズ")
        synthesizer = MockSpeechSynthesizer()

        completed = run_conversation_loop(
            recorder=MockAudioRecorder(),
            transcriber=MockTranscriber("おしまい"),
            reply_generator=MockReplyGenerator("呼ばれない"),
            synthesizer=synthesizer,
            player=MockAudioPlayer(),
            input_path=Path("input.wav"),
            speech_output=Path("reply.wav"),
            duration=0.1,
            sample_rate=16000,
            language="ja",
            turns=1,
            pause=0,
            handle_child_game=game.handle,
            child_game_active=lambda: game.active,
            output=lambda _: None,
        )

        self.assertEqual(completed, 1)
        self.assertEqual(
            synthesizer.inputs,
            ["ゲームはおしまい。また遊ぼうね。"],
        )

    def test_negative_turns_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "turns"):
            run_conversation_loop(
                recorder=MockAudioRecorder(),
                transcriber=MockTranscriber(),
                reply_generator=MockReplyGenerator(),
                synthesizer=MockSpeechSynthesizer(),
                player=MockAudioPlayer(),
                input_path=Path("input.wav"),
                speech_output=Path("reply.wav"),
                duration=0.1,
                sample_rate=16000,
                language="ja",
                turns=-1,
                pause=0,
            )

    def test_negative_silence_limit_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "max silence turns"):
            run_conversation_loop(
                recorder=MockAudioRecorder(),
                transcriber=MockTranscriber(),
                reply_generator=MockReplyGenerator(),
                synthesizer=MockSpeechSynthesizer(),
                player=MockAudioPlayer(),
                input_path=Path("input.wav"),
                speech_output=Path("reply.wav"),
                duration=0.1,
                sample_rate=16000,
                language="ja",
                turns=1,
                pause=0,
                max_silence_turns=-1,
            )

    def test_vad_timeout_skips_all_openai_style_processing(self) -> None:
        logs: list[str] = []
        reply_generator = MockReplyGenerator()

        completed = run_conversation_loop(
            recorder=NoSpeechRecorder(),
            transcriber=MockTranscriber("should-not-run"),
            reply_generator=reply_generator,
            synthesizer=MockSpeechSynthesizer(),
            player=MockAudioPlayer(),
            input_path=Path("input.wav"),
            speech_output=Path("reply.wav"),
            duration=1,
            sample_rate=16000,
            language="ja",
            turns=1,
            pause=0,
            output=logs.append,
        )

        self.assertEqual(completed, 1)
        self.assertEqual(reply_generator.inputs, [])
        self.assertEqual(
            logs,
            [
                "turn=1 listening=true",
                "turn=1 transcript=not-found reason=no-speech",
            ],
        )

    def test_two_silent_turns_end_session_and_return_to_waiting(self) -> None:
        with TemporaryDirectory() as directory:
            logs: list[str] = []
            synthesizer = MockSpeechSynthesizer()
            player = MockAudioPlayer()

            completed = run_conversation_loop(
                recorder=NoSpeechRecorder(),
                transcriber=MockTranscriber("should-not-run"),
                reply_generator=MockReplyGenerator(),
                synthesizer=synthesizer,
                player=player,
                input_path=Path(directory) / "input.wav",
                speech_output=Path(directory) / "reply.wav",
                duration=1,
                sample_rate=16000,
                language="ja",
                turns=2,
                pause=0,
                retry_replies=CHILD_RETRY_REPLIES,
                output=logs.append,
            )

            self.assertEqual(completed, 2)
            self.assertEqual(
                synthesizer.inputs,
                [CHILD_RETRY_REPLIES[0], DEFAULT_INACTIVITY_REPLY],
            )
            self.assertEqual(len(player.played), 2)
            self.assertTrue(
                any("reason=conversation-ended-inactivity" in log for log in logs)
            )

    def test_silence_auto_end_can_be_disabled(self) -> None:
        synthesizer = MockSpeechSynthesizer()

        completed = run_conversation_loop(
            recorder=NoSpeechRecorder(),
            transcriber=MockTranscriber("should-not-run"),
            reply_generator=MockReplyGenerator(),
            synthesizer=synthesizer,
            player=MockAudioPlayer(),
            input_path=Path("input.wav"),
            speech_output=Path("reply.wav"),
            duration=1,
            sample_rate=16000,
            language="ja",
            turns=2,
            pause=0,
            max_silence_turns=0,
            output=lambda _: None,
        )

        self.assertEqual(completed, 2)
        self.assertEqual(synthesizer.inputs, [])

    def test_successful_transcript_resets_child_retry_counter(self) -> None:
        class OneMissRecorder(MockAudioRecorder):
            def __init__(self) -> None:
                self.calls = 0

            def record(
                self, output: Path, *, duration: float, sample_rate: int
            ) -> Path:
                self.calls += 1
                if self.calls in (1, 3):
                    raise NoSpeechDetectedError("no speech")
                return super().record(
                    output, duration=duration, sample_rate=sample_rate
                )

        with TemporaryDirectory() as directory:
            synthesizer = MockSpeechSynthesizer()

            run_conversation_loop(
                recorder=OneMissRecorder(),
                transcriber=MockTranscriber("こんにちは"),
                reply_generator=MockReplyGenerator("やあ"),
                synthesizer=synthesizer,
                player=MockAudioPlayer(),
                input_path=Path(directory) / "input.wav",
                speech_output=Path(directory) / "reply.wav",
                duration=1,
                sample_rate=16000,
                language="ja",
                turns=3,
                pause=0,
                retry_replies=CHILD_RETRY_REPLIES,
                output=lambda _: None,
            )

            self.assertEqual(
                synthesizer.inputs,
                [CHILD_RETRY_REPLIES[0], "やあ", CHILD_RETRY_REPLIES[0]],
            )

    def test_child_mode_retries_instead_of_using_unreliable_transcript(self) -> None:
        with TemporaryDirectory() as directory:
            logs: list[str] = []
            reply_generator = MockReplyGenerator("呼ばれない")
            synthesizer = MockSpeechSynthesizer()

            run_conversation_loop(
                recorder=MockAudioRecorder(),
                transcriber=MockTranscriber("ご視聴ありがとうございました。"),
                reply_generator=reply_generator,
                synthesizer=synthesizer,
                player=MockAudioPlayer(),
                input_path=Path(directory) / "input.wav",
                speech_output=Path(directory) / "reply.wav",
                duration=1,
                sample_rate=16000,
                language="ja",
                turns=1,
                pause=0,
                retry_replies=CHILD_RETRY_REPLIES,
                reject_transcript=is_unreliable_child_transcript,
                output=logs.append,
            )

            self.assertEqual(reply_generator.inputs, [])
            self.assertEqual(synthesizer.inputs, [CHILD_RETRY_REPLIES[0]])
            self.assertTrue(
                any("reason=uncertain-transcript" in log for log in logs)
            )


if __name__ == "__main__":
    unittest.main()
