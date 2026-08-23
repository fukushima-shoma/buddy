import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from robot.audio import (
    AlsaAudioPlayer,
    AlsaAudioRecorder,
    MockAudioPlayer,
    MockAudioRecorder,
    generate_tone,
    inspect_wav,
)
from robot.audio_cli import build_parser


class AudioTest(unittest.TestCase):
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

    def test_cli_defaults_are_hardware_safe(self) -> None:
        record = build_parser().parse_args(["record"])
        play = build_parser().parse_args(["play", "tone.wav"])

        self.assertEqual(record.backend, "mock")
        self.assertEqual(record.sample_rate, 16000)
        self.assertEqual(play.backend, "mock")


if __name__ == "__main__":
    unittest.main()
