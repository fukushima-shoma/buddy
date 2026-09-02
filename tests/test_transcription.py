from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from robot.audio import generate_tone
from robot.transcribe_cli import build_parser, create_transcriber, main
from robot.transcription import (
    CHILD_TRANSCRIPTION_PROMPT,
    DEFAULT_TRANSCRIPTION_MODEL,
    MockTranscriber,
    OpenAITranscriber,
    is_unreliable_child_transcript,
    is_unreliable_transcript,
)


class FakeTranscriptions:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(text="  こんにちは  ")


class TranscriptionTest(unittest.TestCase):
    def test_mock_transcriber_is_deterministic(self) -> None:
        transcriber = MockTranscriber("テスト成功")

        result = transcriber.transcribe(Path("input.wav"), language="ja")

        self.assertEqual(result, "テスト成功")
        self.assertEqual(transcriber.sources, [Path("input.wav")])

    def test_openai_transcriber_sends_file_model_and_language(self) -> None:
        with TemporaryDirectory() as directory:
            source = generate_tone(Path(directory) / "speech.wav", duration=0.1)
            transcriptions = FakeTranscriptions()
            client = SimpleNamespace(
                audio=SimpleNamespace(transcriptions=transcriptions)
            )
            transcriber = OpenAITranscriber(client=client)

            result = transcriber.transcribe(source, language="ja")

            self.assertEqual(result, "こんにちは")
            self.assertEqual(transcriptions.calls[0]["model"], DEFAULT_TRANSCRIPTION_MODEL)
            self.assertEqual(transcriptions.calls[0]["language"], "ja")
            uploaded = transcriptions.calls[0]["file"]
            self.assertEqual(Path(uploaded.name), source)
            self.assertTrue(uploaded.closed)

    def test_openai_transcriber_sends_optional_child_context_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            source = generate_tone(Path(directory) / "speech.wav", duration=0.1)
            transcriptions = FakeTranscriptions()
            client = SimpleNamespace(
                audio=SimpleNamespace(transcriptions=transcriptions)
            )
            transcriber = OpenAITranscriber(
                prompt=CHILD_TRANSCRIPTION_PROMPT,
                client=client,
            )

            transcriber.transcribe(source, language="ja")

            self.assertEqual(
                transcriptions.calls[0]["prompt"], CHILD_TRANSCRIPTION_PROMPT
            )

    def test_child_transcript_filter_rejects_common_hallucinations(self) -> None:
        self.assertTrue(
            is_unreliable_child_transcript("ご視聴ありがとうございました。")
        )
        self.assertTrue(is_unreliable_child_transcript("……"))
        self.assertFalse(is_unreliable_child_transcript("あか"))
        self.assertFalse(is_unreliable_child_transcript("でんしゃがすき"))

    def test_general_transcript_filter_is_conservative(self) -> None:
        self.assertTrue(is_unreliable_transcript("字幕提供：……"))
        self.assertTrue(is_unreliable_transcript("……"))
        self.assertTrue(is_unreliable_transcript("あ" * 201))
        self.assertFalse(is_unreliable_transcript("今日はいい天気だね"))
        self.assertFalse(is_unreliable_transcript("ついてきて"))

    def test_cli_defaults_do_not_call_openai_or_audio_hardware(self) -> None:
        file_args = build_parser().parse_args(["file", "speech.wav"])
        record_args = build_parser().parse_args(["record"])

        self.assertEqual(file_args.backend, "mock")
        self.assertEqual(file_args.model, DEFAULT_TRANSCRIPTION_MODEL)
        self.assertIsNone(file_args.transcription_prompt)
        self.assertEqual(file_args.reply_backend, "none")
        self.assertFalse(file_args.child_mode)
        self.assertEqual(file_args.speech_backend, "none")
        self.assertEqual(file_args.playback_backend, "none")
        self.assertEqual(record_args.backend, "mock")
        self.assertEqual(record_args.audio_backend, "mock")
        self.assertEqual(record_args.reply_backend, "none")
        self.assertFalse(record_args.child_mode)
        self.assertEqual(record_args.speech_backend, "none")
        self.assertEqual(record_args.playback_backend, "none")

    def test_transcriber_factory_defaults_to_mock(self) -> None:
        transcriber = create_transcriber(
            "mock", model=DEFAULT_TRANSCRIPTION_MODEL, mock_text="安全"
        )

        self.assertIsInstance(transcriber, MockTranscriber)

    def test_empty_transcript_skips_reply_generation(self) -> None:
        output = StringIO()
        argv = [
            "robot.transcribe_cli",
            "file",
            "unused.wav",
            "--backend",
            "mock",
            "--mock-text",
            "",
            "--reply-backend",
            "openai",
        ]

        with patch("sys.argv", argv), redirect_stdout(output):
            result = main()

        self.assertEqual(result, 0)
        self.assertIn("transcript=not-found", output.getvalue())
        self.assertIn("reply=skipped reason=empty-transcript", output.getvalue())


if __name__ == "__main__":
    unittest.main()
