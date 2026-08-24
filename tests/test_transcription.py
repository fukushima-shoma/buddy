from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from robot.audio import generate_tone
from robot.transcribe_cli import build_parser, create_transcriber
from robot.transcription import (
    DEFAULT_TRANSCRIPTION_MODEL,
    MockTranscriber,
    OpenAITranscriber,
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

    def test_cli_defaults_do_not_call_openai_or_audio_hardware(self) -> None:
        file_args = build_parser().parse_args(["file", "speech.wav"])
        record_args = build_parser().parse_args(["record"])

        self.assertEqual(file_args.backend, "mock")
        self.assertEqual(file_args.model, DEFAULT_TRANSCRIPTION_MODEL)
        self.assertEqual(record_args.backend, "mock")
        self.assertEqual(record_args.audio_backend, "mock")

    def test_transcriber_factory_defaults_to_mock(self) -> None:
        transcriber = create_transcriber(
            "mock", model=DEFAULT_TRANSCRIPTION_MODEL, mock_text="安全"
        )

        self.assertIsInstance(transcriber, MockTranscriber)


if __name__ == "__main__":
    unittest.main()
