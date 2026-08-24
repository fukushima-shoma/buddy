from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from robot.audio import inspect_wav
from robot.speech import (
    DEFAULT_SPEECH_INSTRUCTIONS,
    DEFAULT_SPEECH_MODEL,
    DEFAULT_SPEECH_VOICE,
    MockSpeechSynthesizer,
    OpenAISpeechSynthesizer,
)
from robot.speech_cli import build_parser, create_synthesizer


class FakeSpeechResponse:
    def __init__(self, audio: bytes = b"RIFF-fake-wav") -> None:
        self.audio = audio
        self.output: Path | None = None

    def __enter__(self) -> "FakeSpeechResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def stream_to_file(self, output: Path) -> None:
        self.output = output
        output.write_bytes(self.audio)


class FakeStreamingSpeech:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.response = FakeSpeechResponse()

    def create(self, **kwargs: object) -> FakeSpeechResponse:
        self.calls.append(kwargs)
        return self.response


class SpeechTest(unittest.TestCase):
    def test_mock_synthesizer_creates_valid_wav(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "reply.wav"
            synthesizer = MockSpeechSynthesizer()

            result = synthesizer.synthesize("こんにちは", output)

            self.assertEqual(result, output)
            self.assertEqual(synthesizer.inputs, ["こんにちは"])
            self.assertGreater(inspect_wav(output).frames, 0)

    def test_openai_synthesizer_uses_speech_api_and_wav(self) -> None:
        with TemporaryDirectory() as directory:
            streaming = FakeStreamingSpeech()
            client = type(
                "Client",
                (),
                {
                    "audio": type(
                        "Audio",
                        (),
                        {
                            "speech": type(
                                "Speech",
                                (),
                                {"with_streaming_response": streaming},
                            )()
                        },
                    )()
                },
            )()
            output = Path(directory) / "nested" / "reply.wav"
            synthesizer = OpenAISpeechSynthesizer(client=client)

            result = synthesizer.synthesize("おはよう", output)

            self.assertEqual(result, output)
            self.assertEqual(output.read_bytes(), b"RIFF-fake-wav")
            self.assertEqual(
                streaming.calls,
                [
                    {
                        "model": DEFAULT_SPEECH_MODEL,
                        "voice": DEFAULT_SPEECH_VOICE,
                        "input": "おはよう",
                        "instructions": DEFAULT_SPEECH_INSTRUCTIONS,
                        "response_format": "wav",
                    }
                ],
            )

    def test_openai_synthesizer_rejects_empty_text(self) -> None:
        streaming = FakeStreamingSpeech()
        client = type(
            "Client",
            (),
            {
                "audio": type(
                    "Audio",
                    (),
                    {
                        "speech": type(
                            "Speech", (), {"with_streaming_response": streaming}
                        )()
                    },
                )()
            },
        )()
        synthesizer = OpenAISpeechSynthesizer(client=client)

        with self.assertRaisesRegex(ValueError, "empty text"):
            synthesizer.synthesize("  ", Path("unused.wav"))

        self.assertEqual(streaming.calls, [])

    def test_cli_defaults_are_hardware_and_api_safe(self) -> None:
        args = build_parser().parse_args(["こんにちは"])

        self.assertEqual(args.backend, "mock")
        self.assertEqual(args.playback_backend, "none")
        self.assertEqual(args.voice, DEFAULT_SPEECH_VOICE)

    def test_factory_defaults_to_mock(self) -> None:
        synthesizer = create_synthesizer(
            "mock", model=DEFAULT_SPEECH_MODEL, voice=DEFAULT_SPEECH_VOICE
        )

        self.assertIsInstance(synthesizer, MockSpeechSynthesizer)


if __name__ == "__main__":
    unittest.main()
