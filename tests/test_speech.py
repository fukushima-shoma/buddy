from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace

from robot.audio import inspect_wav
from robot.speech import (
    DEFAULT_SPEECH_INSTRUCTIONS,
    DEFAULT_SPEECH_MODEL,
    DEFAULT_SPEECH_SPEED,
    DEFAULT_SPEECH_STYLE,
    DEFAULT_SPEECH_VOICE,
    MockSpeechSynthesizer,
    OpenAISpeechSynthesizer,
    SPEECH_STYLE_INSTRUCTIONS,
    get_speech_instructions,
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

    def iter_bytes(self, chunk_size: int | None = None):
        size = chunk_size or len(self.audio)
        for offset in range(0, len(self.audio), size):
            yield self.audio[offset : offset + size]


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
                        "speed": DEFAULT_SPEECH_SPEED,
                    }
                ],
            )

    def test_audio_cache_restores_overwritten_output_and_separates_voice(self) -> None:
        streaming = FakeStreamingSpeech()
        client = SimpleNamespace(
            audio=SimpleNamespace(
                speech=SimpleNamespace(with_streaming_response=streaming)
            )
        )
        synth = OpenAISpeechSynthesizer(client=client)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "reply.wav"
            synth.synthesize("こんにちは", path)
            self.assertFalse(synth.last_cache_hit)
            path.write_bytes(b"overwritten")
            synth.synthesize("こんにちは", path)
            self.assertTrue(synth.last_cache_hit)
            self.assertEqual(path.read_bytes(), b"RIFF-fake-wav")
            self.assertEqual(len(streaming.calls), 1)
            synth.voice = "different"
            synth.synthesize("こんにちは", path)
            self.assertFalse(synth.last_cache_hit)
            self.assertEqual(len(streaming.calls), 2)

    def test_openai_synthesizer_streams_and_saves_wav(self) -> None:
        streaming = FakeStreamingSpeech()
        streaming.response.audio = b"RIFF" + b"audio" * 5000
        client = SimpleNamespace(
            audio=SimpleNamespace(
                speech=SimpleNamespace(with_streaming_response=streaming)
            )
        )
        synth = OpenAISpeechSynthesizer(client=client)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "reply.wav"

            chunks = list(synth.stream("こんにちは", path))

            self.assertGreater(len(chunks), 1)
            self.assertEqual(b"".join(chunks), streaming.response.audio)
            self.assertEqual(path.read_bytes(), streaming.response.audio)
            self.assertFalse(synth.last_cache_hit)

            cached_chunks = list(synth.stream("こんにちは", path))
            self.assertEqual(cached_chunks, [streaming.response.audio])
            self.assertTrue(synth.last_cache_hit)
            self.assertEqual(len(streaming.calls), 1)

    def test_audio_cache_evicts_old_entries(self) -> None:
        streaming = FakeStreamingSpeech()
        client = SimpleNamespace(
            audio=SimpleNamespace(
                speech=SimpleNamespace(with_streaming_response=streaming)
            )
        )
        synth = OpenAISpeechSynthesizer(client=client)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "reply.wav"
            for number in range(33):
                synth.synthesize(str(number), path)
            synth.synthesize("32", path)
            self.assertEqual(len(streaming.calls), 33)
            synth.synthesize("0", path)
            self.assertEqual(len(streaming.calls), 34)

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
        self.assertEqual(args.voice, "coral")
        self.assertEqual(args.style, "calm")
        self.assertEqual(args.speed, DEFAULT_SPEECH_SPEED)

    def test_default_calm_style_targets_a_gentle_youthful_voice(self) -> None:
        instructions = get_speech_instructions(DEFAULT_SPEECH_STYLE)

        self.assertIn("幼さのある中性的な声色", instructions)
        self.assertIn("リラックス", instructions)
        self.assertIn("少し年上の子どもの友だち", instructions)
        self.assertIn("少しゆっくり", instructions)
        self.assertIn("自然な抑揚", instructions)
        self.assertIn("内容に合わせて声の表情を変えて", instructions)

    def test_speech_speed_must_be_supported_by_the_api(self) -> None:
        streaming = FakeStreamingSpeech()
        client = SimpleNamespace(
            audio=SimpleNamespace(
                speech=SimpleNamespace(with_streaming_response=streaming)
            )
        )

        with self.assertRaisesRegex(ValueError, "between 0.25 and 4.0"):
            OpenAISpeechSynthesizer(speed=0.1, client=client)

    def test_speech_styles_have_distinct_instructions(self) -> None:
        self.assertEqual(
            get_speech_instructions("buddy"), SPEECH_STYLE_INSTRUCTIONS["buddy"]
        )
        self.assertNotEqual(
            get_speech_instructions("cheerful"), get_speech_instructions("calm")
        )

    def test_unknown_speech_style_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported speech style"):
            get_speech_instructions("unknown")

    def test_factory_defaults_to_mock(self) -> None:
        synthesizer = create_synthesizer(
            "mock", model=DEFAULT_SPEECH_MODEL, voice=DEFAULT_SPEECH_VOICE
        )

        self.assertIsInstance(synthesizer, MockSpeechSynthesizer)


if __name__ == "__main__":
    unittest.main()
