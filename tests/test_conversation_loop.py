from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from robot.audio import MockAudioPlayer, MockAudioRecorder
from robot.conversation import MockReplyGenerator
from robot.conversation_loop_cli import build_parser, run_conversation_loop
from robot.speech import MockSpeechSynthesizer
from robot.transcription import MockTranscriber


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


class ConversationLoopTest(unittest.TestCase):
    def test_defaults_are_finite_and_do_not_use_hardware_or_api(self) -> None:
        args = build_parser().parse_args([])

        self.assertEqual(args.turns, 1)
        self.assertEqual(args.audio_backend, "mock")
        self.assertEqual(args.transcription_backend, "mock")
        self.assertEqual(args.reply_backend, "mock")
        self.assertEqual(args.speech_backend, "mock")
        self.assertEqual(args.playback_backend, "mock")

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


if __name__ == "__main__":
    unittest.main()
