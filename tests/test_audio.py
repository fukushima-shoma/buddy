from __future__ import annotations

from array import array
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from robot.audio import (
    AlsaAudioPlayer,
    AlsaAudioRecorder,
    AlsaVoiceActivatedRecorder,
    InterruptibleAlsaAudioPlayer,
    MockAudioPlayer,
    MockAudioRecorder,
    NoSpeechDetectedError,
    generate_tone,
    inspect_wav,
    pcm16_rms,
)
from robot.audio_cli import build_parser


class AudioTest(unittest.TestCase):
    class FakeStdout:
        def __init__(self, chunks: list[bytes]) -> None:
            self.chunks = list(chunks)

        def read(self, size: int) -> bytes:
            if not self.chunks:
                return b""
            chunk = self.chunks.pop(0)
            if len(chunk) != size:
                raise AssertionError(f"expected {size} bytes, got {len(chunk)}")
            return chunk

    class FakeProcess:
        def __init__(self, chunks: list[bytes]) -> None:
            self.stdout = AudioTest.FakeStdout(chunks)
            self.running = True
            self.terminated = False

        def poll(self) -> int | None:
            return None if self.running else 0

        def terminate(self) -> None:
            self.terminated = True
            self.running = False

        def wait(self, timeout: float | None = None) -> int:
            self.running = False
            return 0

        def kill(self) -> None:
            self.running = False

    @staticmethod
    def pcm_chunk(level: int, frames: int = 100) -> bytes:
        return array("h", [level] * frames).tobytes()

    def test_generates_inspectable_test_tone(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "tone.wav"
            generate_tone(output, duration=0.25, sample_rate=8000)

            info = inspect_wav(output)

            self.assertEqual(info.channels, 1)
            self.assertEqual(info.sample_width, 2)
            self.assertEqual(info.sample_rate, 8000)
            self.assertEqual(info.frames, 2000)
            self.assertAlmostEqual(info.duration, 0.25)

    def test_mock_recorder_creates_silent_wav(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "recording.wav"
            MockAudioRecorder().record(output, duration=0.5, sample_rate=16000)

            info = inspect_wav(output)

            self.assertEqual(info.frames, 8000)
            self.assertAlmostEqual(info.duration, 0.5)

    def test_mock_player_validates_and_tracks_wav(self) -> None:
        with TemporaryDirectory() as directory:
            source = generate_tone(Path(directory) / "tone.wav")
            player = MockAudioPlayer()

            player.play(source)

            self.assertEqual(player.played, [source])

    def test_alsa_backends_build_commands_without_a_shell(self) -> None:
        commands: list[list[str]] = []

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            commands.append(command)
            self.assertEqual(kwargs, {"check": True})
            return subprocess.CompletedProcess(command, 0)

        recorder = AlsaAudioRecorder(device="hw:2,0", runner=runner)
        recorder.record(Path("input.wav"), duration=2.1, sample_rate=16000)
        AlsaAudioPlayer(device="hw:2,0", runner=runner).play(Path("output.wav"))

        self.assertEqual(commands[0][0:3], ["arecord", "-D", "hw:2,0"])
        self.assertIn("3", commands[0])
        self.assertEqual(commands[1], ["aplay", "-D", "hw:2,0", "output.wav"])

    def test_interruptible_player_stops_after_sustained_voice(self) -> None:
        playback = self.FakeProcess([])
        capture = self.FakeProcess(
            [self.pcm_chunk(3000), self.pcm_chunk(3200)]
        )
        processes = iter([playback, capture])
        commands: list[list[str]] = []

        def factory(command: list[str], **kwargs: object) -> AudioTest.FakeProcess:
            commands.append(command)
            return next(processes)

        player = InterruptibleAlsaAudioPlayer(
            device="plughw:2,0",
            capture_device="plughw:2,0",
            sample_rate=1000,
            chunk_duration=0.1,
            ignore_duration=0,
            confirm_chunks=2,
            process_factory=factory,
        )

        player.play(Path("reply.wav"))

        self.assertTrue(player.last_interrupted)
        self.assertTrue(playback.terminated)
        self.assertTrue(capture.terminated)
        self.assertEqual(commands[0][0], "aplay")
        self.assertEqual(commands[1][0], "arecord")

    def test_cli_defaults_are_hardware_safe(self) -> None:
        record = build_parser().parse_args(["record"])
        play = build_parser().parse_args(["play", "tone.wav"])

        self.assertEqual(record.backend, "mock")
        self.assertEqual(record.sample_rate, 16000)
        self.assertEqual(play.backend, "mock")

    def test_pcm16_rms_measures_sample_level(self) -> None:
        self.assertEqual(pcm16_rms(self.pcm_chunk(0)), 0.0)
        self.assertAlmostEqual(pcm16_rms(self.pcm_chunk(1200)), 1200.0)

    def test_voice_activated_recorder_stops_after_trailing_silence(self) -> None:
        with TemporaryDirectory() as directory:
            chunks = [
                self.pcm_chunk(0),
                self.pcm_chunk(1000),
                self.pcm_chunk(1200),
                self.pcm_chunk(0),
                self.pcm_chunk(0),
            ]
            process = self.FakeProcess(chunks)
            commands: list[list[str]] = []

            def factory(command: list[str], **kwargs: object) -> AudioTest.FakeProcess:
                commands.append(command)
                self.assertEqual(kwargs["stdout"], subprocess.PIPE)
                return process

            output = Path(directory) / "voice.wav"
            recorder = AlsaVoiceActivatedRecorder(
                device="plughw:2,0",
                threshold=500,
                silence_duration=0.2,
                max_wait=1,
                pre_roll=0.1,
                chunk_duration=0.1,
                process_factory=factory,
            )

            result = recorder.record(output, duration=2, sample_rate=1000)

            self.assertEqual(result, output)
            self.assertAlmostEqual(inspect_wav(output).duration, 0.4)
            self.assertIn("raw", commands[0])
            self.assertTrue(process.terminated)

    def test_voice_activated_recorder_times_out_without_speech(self) -> None:
        process = self.FakeProcess([self.pcm_chunk(0), self.pcm_chunk(0)])
        recorder = AlsaVoiceActivatedRecorder(
            threshold=500,
            max_wait=0.2,
            chunk_duration=0.1,
            process_factory=lambda *args, **kwargs: process,
        )

        with self.assertRaises(NoSpeechDetectedError):
            recorder.record(Path("unused.wav"), duration=1, sample_rate=1000)

        self.assertTrue(process.terminated)


if __name__ == "__main__":
    unittest.main()
