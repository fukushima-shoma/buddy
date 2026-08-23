from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import struct
import subprocess
from typing import Callable, Protocol, Sequence
import wave


@dataclass(frozen=True)
class WavInfo:
    channels: int
    sample_width: int
    sample_rate: int
    frames: int

    @property
    def duration(self) -> float:
        if self.sample_rate <= 0:
            return 0.0
        return self.frames / self.sample_rate


class AudioRecorder(Protocol):
    def record(
        self,
        output: Path,
        *,
        duration: float,
        sample_rate: int,
    ) -> Path:
        """Record mono 16-bit PCM audio to a WAV file."""


class AudioPlayer(Protocol):
    def play(self, source: Path) -> None:
        """Play a WAV file and return after playback finishes."""


def _write_mono_pcm16(output: Path, sample_rate: int, samples: Sequence[int]) -> Path:
    output = output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(max(1, sample_rate))
        wav_file.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
    return output


def generate_tone(
    output: Path,
    *,
    frequency: float = 440.0,
    duration: float = 1.0,
    sample_rate: int = 16000,
    volume: float = 0.2,
) -> Path:
    """Generate a mono 16-bit PCM WAV tone for speaker testing."""
    sample_rate = max(1, sample_rate)
    frame_count = max(0, round(max(0.0, duration) * sample_rate))
    amplitude = round(32767 * min(1.0, max(0.0, volume)))
    frequency = max(0.0, frequency)
    samples = [
        round(amplitude * math.sin(2 * math.pi * frequency * index / sample_rate))
        for index in range(frame_count)
    ]
    return _write_mono_pcm16(output, sample_rate, samples)


def inspect_wav(source: Path) -> WavInfo:
    with wave.open(str(source.expanduser()), "rb") as wav_file:
        return WavInfo(
            channels=wav_file.getnchannels(),
            sample_width=wav_file.getsampwidth(),
            sample_rate=wav_file.getframerate(),
            frames=wav_file.getnframes(),
        )


class MockAudioRecorder:
    def record(
        self,
        output: Path,
        *,
        duration: float,
        sample_rate: int,
    ) -> Path:
        frame_count = max(0, round(max(0.0, duration) * max(1, sample_rate)))
        return _write_mono_pcm16(output, sample_rate, [0] * frame_count)


class MockAudioPlayer:
    def __init__(self) -> None:
        self.played: list[Path] = []

    def play(self, source: Path) -> None:
        inspect_wav(source)
        self.played.append(source.expanduser())


class AlsaAudioRecorder:
    def __init__(
        self,
        device: str = "default",
        runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    ) -> None:
        self.device = device
        self._runner = runner

    def record(
        self,
        output: Path,
        *,
        duration: float,
        sample_rate: int,
    ) -> Path:
        output = output.expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "arecord",
            "-D",
            self.device,
            "-c",
            "1",
            "-f",
            "S16_LE",
            "-r",
            str(max(1, sample_rate)),
            "-d",
            str(max(1, math.ceil(duration))),
            str(output),
        ]
        self._runner(command, check=True)
        return output


class AlsaAudioPlayer:
    def __init__(
        self,
        device: str = "default",
        runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    ) -> None:
        self.device = device
        self._runner = runner

    def play(self, source: Path) -> None:
        self._runner(
            ["aplay", "-D", self.device, str(source.expanduser())],
            check=True,
        )
