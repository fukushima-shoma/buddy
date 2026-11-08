from __future__ import annotations

from array import array
import json
import subprocess
from threading import Event
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import wave

from robot.audio import (
    AlsaAudioPlayer,
    AlsaAudioRecorder,
    AlsaVoiceActivatedRecorder,
    InterruptibleAlsaAudioPlayer,
    MockAudioPlayer,
    MockAudioRecorder,
    NoSpeechDetectedError,
    generate_engine_rev,
    generate_tone,
    generate_tone_sequence,
    inspect_wav,
    pcm16_rms,
)
from robot.audio_cli import build_parser


class AudioTest(unittest.TestCase):
    class FakeStopRecognizer:
        def __init__(self) -> None:
            self.calls = 0
            self.reset_calls = 0

        def Reset(self) -> None:
            self.calls = 0
            self.reset_calls += 1

        def AcceptWaveform(self, chunk: bytes) -> bool:
            self.calls += 1
            return False

        def PartialResult(self) -> str:
            text = "止まって" if self.calls >= 2 else "止ま"
            return json.dumps({"partial": text}, ensure_ascii=False)

        def Result(self) -> str:
            return '{"text": ""}'

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

    class FakeStdin:
        def __init__(self) -> None:
            self.data = bytearray()
            self.closed = False

        def write(self, chunk: bytes) -> int:
            self.data.extend(chunk)
            return len(chunk)

        def close(self) -> None:
            self.closed = True

    class FakeStreamingProcess:
        def __init__(self) -> None:
            self.stdin = AudioTest.FakeStdin()
            self.running = True

        def poll(self) -> int | None:
            return None if self.running else 0

        def terminate(self) -> None:
            self.running = False

        def wait(self, timeout: float | None = None) -> int:
            self.running = False
            return 0

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

    def test_generates_short_two_tone_acknowledgement(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "chime.wav"
            generate_tone_sequence(
                output,
                frequencies=(660, 990),
                tone_duration=0.1,
                gap_duration=0.02,
                sample_rate=8000,
            )

            info = inspect_wav(output)

            self.assertEqual(info.frames, 1760)
            self.assertAlmostEqual(info.duration, 0.22)

    def test_generates_short_engine_acknowledgement(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "engine.wav"
            generate_engine_rev(output, duration=0.38, sample_rate=8000)

            info = inspect_wav(output)

            self.assertEqual(info.frames, 3040)
            self.assertAlmostEqual(info.duration, 0.38)

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

    def test_alsa_player_writes_stream_to_aplay_stdin(self) -> None:
        process = self.FakeStreamingProcess()
        commands: list[list[str]] = []
        first_chunks: list[str] = []

        def factory(command: list[str], **kwargs: object) -> AudioTest.FakeStreamingProcess:
            commands.append(command)
            self.assertIs(kwargs["stdin"], subprocess.PIPE)
            return process

        player = AlsaAudioPlayer(device="hw:2,0", process_factory=factory)
        player.play_stream(
            iter((b"RIFF", b"audio")),
            on_first_chunk=lambda: first_chunks.append("started"),
        )

        self.assertEqual(commands, [["aplay", "-D", "hw:2,0", "-"]])
        self.assertEqual(process.stdin.data, b"RIFFaudio")
        self.assertTrue(process.stdin.closed)
        self.assertEqual(first_chunks, ["started"])

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

    def test_raw_pcm_player_uses_explicit_format(self) -> None:
        process = self.FakeStreamingProcess()
        commands = []

        def factory(command, **kwargs):
            commands.append(command)
            return process

        AlsaAudioPlayer(process_factory=factory).play_pcm16_stream(iter((b"\x00\x01",)))
        self.assertEqual(commands[0], ["aplay", "-D", "default", "-t", "raw",
                                      "-f", "S16_LE", "-c", "1", "-r", "24000", "-"])
        self.assertEqual(process.stdin.data, b"\x00\x01")

    def test_interrupt_callback_unblocks_receiver_before_join(self) -> None:
        first_write = Event()
        cancelled = Event()
        finished = Event()

        class StreamingInput(AudioTest.FakeStdin):
            def write(self, chunk):
                first_write.set()
                return super().write(chunk)

        playback = self.FakeStreamingProcess()
        playback.stdin = StreamingInput()
        capture = self.FakeProcess([self.pcm_chunk(3000)] * 2)
        original_read = capture.stdout.read

        def read(size):
            assert first_write.wait(1)
            return original_read(size)

        capture.stdout.read = read
        processes = iter((playback, capture))
        player = InterruptibleAlsaAudioPlayer(
            sample_rate=1000, chunk_duration=0.1, ignore_duration=0,
            confirm_chunks=2, process_factory=lambda *a, **k: next(processes),
        )

        def chunks():
            try:
                yield b"\x00\x01"
                assert cancelled.wait(1), "receiver was not cancelled"
                raise RuntimeError("cancelled receiver")
            finally:
                finished.set()

        player.play_pcm16_stream(chunks(), on_interrupt=cancelled.set)
        self.assertTrue(player.last_interrupted)
        self.assertTrue(cancelled.is_set())
        self.assertTrue(finished.is_set())

    def test_interruptible_player_monitors_voice_while_streaming(self) -> None:
        first_write = Event()

        class StreamingInput(AudioTest.FakeStdin):
            def write(self, chunk: bytes) -> int:
                written = super().write(chunk)
                first_write.set()
                return written

        class StreamingPlayback(AudioTest.FakeStreamingProcess):
            def __init__(self) -> None:
                super().__init__()
                self.stdin = StreamingInput()
                self.terminated = False

            def terminate(self) -> None:
                self.terminated = True
                super().terminate()

        class WaitingCapture(AudioTest.FakeProcess):
            def __init__(self) -> None:
                super().__init__([AudioTest.pcm_chunk(3000)] * 2)
                original_read = self.stdout.read

                def read(size: int) -> bytes:
                    if not first_write.wait(timeout=1):
                        raise AssertionError("playback stream did not start")
                    return original_read(size)

                self.stdout.read = read

        playback = StreamingPlayback()
        capture = WaitingCapture()
        processes = iter((playback, capture))
        player = InterruptibleAlsaAudioPlayer(
            sample_rate=1000,
            chunk_duration=0.1,
            ignore_duration=0,
            confirm_chunks=2,
            process_factory=lambda *args, **kwargs: next(processes),
        )

        player.play_stream(iter((b"RIFF", b"audio")))

        self.assertTrue(playback.terminated)
        self.assertTrue(capture.terminated)
        self.assertTrue(player.last_interrupted)
        self.assertTrue(first_write.is_set())

    def test_interruptible_player_detects_local_stop_word_once(self) -> None:
        playback = self.FakeProcess([])
        capture = self.FakeProcess([self.pcm_chunk(100), self.pcm_chunk(100)])
        processes = iter([playback, capture])
        recognizer = self.FakeStopRecognizer()

        player = InterruptibleAlsaAudioPlayer(
            sample_rate=1000,
            chunk_duration=0.1,
            ignore_duration=0.6,
            threshold=10000,
            stop_recognizer=recognizer,
            process_factory=lambda *args, **kwargs: next(processes),
        )

        player.play(Path("reply.wav"))

        self.assertTrue(playback.terminated)
        self.assertTrue(player.last_interrupted)
        self.assertTrue(player.consume_stop_request())
        self.assertFalse(player.consume_stop_request())
        self.assertEqual(recognizer.reset_calls, 1)

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

    def test_capture_ready_is_notified_once_before_speech_upload(self) -> None:
        process = self.FakeProcess([self.pcm_chunk(0), self.pcm_chunk(1200),
                                    self.pcm_chunk(0), self.pcm_chunk(0)])
        recorder = AlsaVoiceActivatedRecorder(
            silence_duration=0.2, chunk_duration=0.1,
            process_factory=lambda *a, **k: process,
        )
        events = []
        with TemporaryDirectory() as directory:
            recorder.record_streaming(
                Path(directory) / "audio.wav", duration=2, sample_rate=1000,
                on_ready=lambda: events.append("ready"),
                on_chunk=lambda _: events.append("upload"),
            )
        self.assertEqual(events.count("ready"), 1)
        self.assertEqual(events[0], "ready")
        self.assertIn("upload", events)
        self.assertTrue(process.terminated)

    def test_failed_capture_does_not_announce_ready(self) -> None:
        process = self.FakeProcess([])
        recorder = AlsaVoiceActivatedRecorder(process_factory=lambda *a, **k: process)
        events = []
        with self.assertRaises(RuntimeError):
            recorder.record(Path("unused.wav"), duration=1, sample_rate=1000,
                            on_ready=lambda: events.append("ready"))
        self.assertEqual(events, [])
        self.assertTrue(process.terminated)

    def test_streamed_capture_matches_wav_without_waiting_silence(self) -> None:
        chunks = [self.pcm_chunk(0)] * 4 + [self.pcm_chunk(1200)] + [self.pcm_chunk(0)] * 2
        process = self.FakeProcess(chunks)
        recorder = AlsaVoiceActivatedRecorder(
            threshold=500, max_wait=1, pre_roll=0.2, silence_duration=0.2,
            chunk_duration=0.1, process_factory=lambda *a, **k: process,
        )
        sent = []
        with TemporaryDirectory() as directory:
            output = recorder.record_streaming(
                Path(directory) / "audio.wav", duration=2, sample_rate=1000,
                on_chunk=sent.append,
            )
            with wave.open(str(output), "rb") as audio:
                self.assertEqual(b"".join(sent), audio.readframes(audio.getnframes()))
        self.assertEqual(sent, chunks[3:])

    def test_semantic_capture_keeps_pause_then_resumed_speech(self) -> None:
        chunks = [self.pcm_chunk(1200)] + [self.pcm_chunk(0)] * 12 + [self.pcm_chunk(1300)] + [self.pcm_chunk(0)] * 2
        process = self.FakeProcess(chunks)
        recorder = AlsaVoiceActivatedRecorder(
            threshold=500, silence_duration=0.4, chunk_duration=0.1,
            process_factory=lambda *a, **k: process,
        )
        sent = []
        with TemporaryDirectory() as directory:
            output = recorder.record_streaming(
                Path(directory) / "audio.wav", duration=20, sample_rate=1000,
                on_chunk=sent.append, should_stop=lambda: not process.stdout.chunks,
            )
            self.assertEqual(inspect_wav(output).frames, 1600)
        self.assertEqual(sent, chunks)
        self.assertEqual(recorder.last_stop_reason, "semantic")

    def test_semantic_capture_still_has_hard_duration_limit(self) -> None:
        process = self.FakeProcess([self.pcm_chunk(1200)] + [self.pcm_chunk(0)] * 20)
        recorder = AlsaVoiceActivatedRecorder(
            threshold=500, silence_duration=0.4, chunk_duration=0.1,
            process_factory=lambda *a, **k: process,
        )
        with TemporaryDirectory() as directory:
            recorder.record_streaming(
                Path(directory) / "audio.wav", duration=1.5, sample_rate=1000,
                on_chunk=lambda chunk: None, should_stop=lambda: False,
            )
        self.assertEqual(recorder.last_stop_reason, "duration-limit")
        self.assertAlmostEqual(recorder.last_duration, 1.5)

    def test_semantic_watchdog_ends_stalled_detector_after_three_seconds_quiet(self) -> None:
        process = self.FakeProcess([self.pcm_chunk(1200)] + [self.pcm_chunk(0)] * 40)
        recorder = AlsaVoiceActivatedRecorder(
            silence_duration=0.4, semantic_silence_duration=3.0, chunk_duration=0.1,
            process_factory=lambda *a, **k: process,
        )
        with TemporaryDirectory() as directory:
            recorder.record_streaming(
                Path(directory) / "audio.wav", duration=20, sample_rate=1000,
                on_chunk=lambda _: None, should_stop=lambda: False,
            )
        self.assertEqual(recorder.last_stop_reason, "semantic-silence-watchdog")
        self.assertAlmostEqual(recorder.last_duration, 3.1)
        self.assertAlmostEqual(recorder.last_trailing_silence, 3.0)
        self.assertTrue(process.terminated)

    def test_resumed_speech_resets_semantic_watchdog(self) -> None:
        chunks = ([self.pcm_chunk(1200)] + [self.pcm_chunk(0)] * 25
                  + [self.pcm_chunk(1300)] + [self.pcm_chunk(0)] * 30)
        process = self.FakeProcess(chunks)
        recorder = AlsaVoiceActivatedRecorder(
            silence_duration=0.4, semantic_silence_duration=3.0, chunk_duration=0.1,
            process_factory=lambda *a, **k: process,
        )
        sent = []
        with TemporaryDirectory() as directory:
            recorder.record_streaming(
                Path(directory) / "audio.wav", duration=20, sample_rate=1000,
                on_chunk=sent.append, should_stop=lambda: False,
            )
        self.assertEqual(sent, chunks)
        self.assertEqual(recorder.last_stop_reason, "semantic-silence-watchdog")


if __name__ == "__main__":
    unittest.main()
