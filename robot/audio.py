from __future__ import annotations

from array import array
from collections import deque
from dataclasses import dataclass
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
from typing import Any, Callable, Protocol, Sequence
import unicodedata
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


class NoSpeechDetectedError(RuntimeError):
    """Raised when voice-activated recording times out before speech starts."""


def _write_mono_pcm16(output: Path, sample_rate: int, samples: Sequence[int]) -> Path:
    output = output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(max(1, sample_rate))
        wav_file.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
    return output


def _write_mono_pcm16_chunks(
    output: Path,
    sample_rate: int,
    chunks: Sequence[bytes],
) -> Path:
    output = output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(max(1, sample_rate))
        wav_file.writeframes(b"".join(chunks))
    return output


def pcm16_rms(chunk: bytes) -> float:
    usable = len(chunk) - (len(chunk) % 2)
    if usable == 0:
        return 0.0
    samples = array("h")
    samples.frombytes(chunk[:usable])
    if sys.byteorder != "little":
        samples.byteswap()
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


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


def generate_tone_sequence(
    output: Path,
    *,
    frequencies: Sequence[float],
    tone_duration: float = 0.11,
    gap_duration: float = 0.025,
    sample_rate: int = 16000,
    volume: float = 0.2,
) -> Path:
    """Generate a short multi-tone cue with fades to avoid audible clicks."""
    sample_rate = max(1, sample_rate)
    tone_frames = max(1, round(max(0.01, tone_duration) * sample_rate))
    gap_frames = max(0, round(max(0.0, gap_duration) * sample_rate))
    amplitude = round(32767 * min(1.0, max(0.0, volume)))
    fade_frames = min(tone_frames // 2, max(1, round(0.01 * sample_rate)))
    samples: list[int] = []
    for tone_index, frequency in enumerate(frequencies):
        frequency = max(0.0, frequency)
        for frame in range(tone_frames):
            fade_in = min(1.0, frame / fade_frames)
            fade_out = min(1.0, (tone_frames - frame - 1) / fade_frames)
            envelope = min(fade_in, fade_out)
            samples.append(
                round(
                    amplitude
                    * envelope
                    * math.sin(2 * math.pi * frequency * frame / sample_rate)
                )
            )
        if tone_index + 1 < len(frequencies):
            samples.extend([0] * gap_frames)
    return _write_mono_pcm16(output, sample_rate, samples)


def generate_engine_rev(
    output: Path,
    *,
    duration: float = 0.38,
    sample_rate: int = 16000,
    volume: float = 0.18,
) -> Path:
    """Generate a short, friendly engine-start cue without recorded audio."""
    sample_rate = max(1, sample_rate)
    frame_count = max(1, round(max(0.1, duration) * sample_rate))
    amplitude = 32767 * min(1.0, max(0.0, volume))
    fade_frames = max(1, round(0.03 * sample_rate))
    phase = 0.0
    samples: list[int] = []
    for frame in range(frame_count):
        progress = frame / max(1, frame_count - 1)
        frequency = 85 + 105 * progress + 12 * math.sin(2 * math.pi * 7 * progress)
        phase += 2 * math.pi * frequency / sample_rate
        fade_in = min(1.0, frame / fade_frames)
        fade_out = min(1.0, (frame_count - frame - 1) / fade_frames)
        envelope = min(fade_in, fade_out) * (0.78 + 0.22 * math.sin(phase * 0.23))
        engine_wave = math.sin(phase) + 0.45 * math.sin(phase * 2)
        samples.append(round(amplitude * envelope * engine_wave / 1.45))
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


class AlsaVoiceActivatedRecorder:
    def __init__(
        self,
        device: str = "default",
        *,
        threshold: float = 500.0,
        silence_duration: float = 0.8,
        max_wait: float = 10.0,
        pre_roll: float = 0.3,
        chunk_duration: float = 0.1,
        process_factory: Callable[..., Any] = subprocess.Popen,
    ) -> None:
        self.device = device
        self.threshold = max(0.0, threshold)
        self.silence_duration = max(0.1, silence_duration)
        self.max_wait = max(0.1, max_wait)
        self.pre_roll = max(0.0, pre_roll)
        self.chunk_duration = max(0.02, chunk_duration)
        self._process_factory = process_factory

    def record(
        self,
        output: Path,
        *,
        duration: float,
        sample_rate: int,
    ) -> Path:
        sample_rate = max(1, sample_rate)
        duration = max(self.chunk_duration, duration)
        chunk_frames = max(1, round(sample_rate * self.chunk_duration))
        chunk_bytes = chunk_frames * 2
        wait_chunks = max(1, math.ceil(self.max_wait / self.chunk_duration))
        record_chunks = max(1, math.ceil(duration / self.chunk_duration))
        trailing_chunks = max(
            1, math.ceil(self.silence_duration / self.chunk_duration)
        )
        pre_roll_chunks = max(1, math.ceil(self.pre_roll / self.chunk_duration))
        buffered: deque[bytes] = deque(maxlen=pre_roll_chunks)
        captured: list[bytes] = []
        command = [
            "arecord",
            "--quiet",
            "-D",
            self.device,
            "-c",
            "1",
            "-f",
            "S16_LE",
            "-r",
            str(sample_rate),
            "-t",
            "raw",
        ]
        process = self._process_factory(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        started = False
        waited = 0
        after_start = 0
        silent = 0
        try:
            if process.stdout is None:
                raise RuntimeError("arecord did not provide an audio stream")
            while True:
                chunk = process.stdout.read(chunk_bytes)
                if len(chunk) != chunk_bytes:
                    raise RuntimeError("arecord stopped before recording completed")
                level = pcm16_rms(chunk)
                if not started:
                    buffered.append(chunk)
                    waited += 1
                    if level >= self.threshold:
                        started = True
                        captured.extend(buffered)
                        after_start = 1
                        if after_start >= record_chunks:
                            break
                    elif waited >= wait_chunks:
                        raise NoSpeechDetectedError(
                            f"No speech detected within {self.max_wait:.1f}s"
                        )
                    continue

                captured.append(chunk)
                after_start += 1
                silent = silent + 1 if level < self.threshold else 0
                if silent >= trailing_chunks or after_start >= record_chunks:
                    break
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        return _write_mono_pcm16_chunks(output, sample_rate, captured)


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


class InterruptibleAlsaAudioPlayer:
    """Stop playback after sustained microphone activity; opt-in due to echo."""

    def __init__(
        self,
        device: str = "default",
        *,
        capture_device: str | None = None,
        threshold: float = 2500.0,
        sample_rate: int = 16000,
        chunk_duration: float = 0.1,
        ignore_duration: float = 0.6,
        confirm_chunks: int = 2,
        stop_word_model: Path | None = None,
        stop_recognizer: Any | None = None,
        process_factory: Callable[..., Any] = subprocess.Popen,
    ) -> None:
        self.device = device
        self.capture_device = capture_device or device
        self.threshold = max(0.0, threshold)
        self.sample_rate = max(1, sample_rate)
        self.chunk_duration = max(0.02, chunk_duration)
        self.ignore_chunks = max(0, math.ceil(ignore_duration / self.chunk_duration))
        self.confirm_chunks = max(1, confirm_chunks)
        self._process_factory = process_factory
        self.last_interrupted = False
        self.last_stop_requested = False
        self._stop_model: Any | None = None
        if stop_recognizer is None and stop_word_model is not None:
            try:
                import vosk
            except ImportError as exc:
                raise RuntimeError(
                    "vosk is required for local stop-word recognition."
                ) from exc
            model_path = stop_word_model.expanduser().resolve()
            if not model_path.is_dir():
                raise RuntimeError(f"Vosk model directory not found: {model_path}")
            vosk.SetLogLevel(-1)
            self._stop_model = vosk.Model(str(model_path))
            grammar = json.dumps(["止まって", "ストップ", "[unk]"], ensure_ascii=False)
            stop_recognizer = vosk.KaldiRecognizer(
                self._stop_model,
                self.sample_rate,
                grammar,
            )
        self._stop_recognizer = stop_recognizer
        self._stop_targets = {"止まって", "とまって", "ストップ"}

    @staticmethod
    def _normalized_recognition(payload: str) -> str:
        try:
            result = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            return ""
        if not isinstance(result, dict):
            return ""
        text = result.get("partial") or result.get("text") or ""
        return "".join(
            character
            for character in unicodedata.normalize("NFKC", str(text)).casefold()
            if character.isalnum()
        )

    def consume_stop_request(self) -> bool:
        requested = self.last_stop_requested
        self.last_stop_requested = False
        return requested

    def play(self, source: Path) -> None:
        playback = self._process_factory(
            ["aplay", "-D", self.device, str(source.expanduser())],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        capture = self._process_factory(
            [
                "arecord", "--quiet", "-D", self.capture_device, "-c", "1",
                "-f", "S16_LE", "-r", str(self.sample_rate), "-t", "raw",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        chunk_bytes = max(1, round(self.sample_rate * self.chunk_duration)) * 2
        active_chunks = 0
        observed_chunks = 0
        self.last_interrupted = False
        self.last_stop_requested = False
        if self._stop_recognizer is not None:
            self._stop_recognizer.Reset()
        try:
            if capture.stdout is None:
                raise RuntimeError("arecord did not provide an audio stream")
            while playback.poll() is None:
                chunk = capture.stdout.read(chunk_bytes)
                if len(chunk) != chunk_bytes:
                    break
                observed_chunks += 1
                if self._stop_recognizer is not None:
                    completed = self._stop_recognizer.AcceptWaveform(chunk)
                    payload = (
                        self._stop_recognizer.Result()
                        if completed
                        else self._stop_recognizer.PartialResult()
                    )
                    if self._normalized_recognition(payload) in self._stop_targets:
                        playback.terminate()
                        playback.wait(timeout=1)
                        self.last_interrupted = True
                        self.last_stop_requested = True
                        break
                if observed_chunks <= self.ignore_chunks:
                    continue
                active_chunks = active_chunks + 1 if pcm16_rms(chunk) >= self.threshold else 0
                if active_chunks >= self.confirm_chunks:
                    playback.terminate()
                    playback.wait(timeout=1)
                    self.last_interrupted = True
                    break
            if playback.poll() is None:
                playback.wait()
        finally:
            if capture.poll() is None:
                capture.terminate()
                try:
                    capture.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    capture.kill()
                    capture.wait()
