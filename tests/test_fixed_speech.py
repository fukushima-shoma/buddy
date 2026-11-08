import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import wave

import pytest

from robot.fixed_speech import FixedSpeechCache, fixed_speech_phrases, MAX_FIXED_AUDIO_BYTES
from robot.fixed_speech_cli import main as prepare
from robot.speech import (
    OpenAISpeechSynthesizer, DEFAULT_SPEECH_MODEL, DEFAULT_SPEECH_VOICE,
    DEFAULT_SPEECH_INSTRUCTIONS, DEFAULT_SPEECH_SPEED,
)


SETTINGS = dict(model=DEFAULT_SPEECH_MODEL, voice=DEFAULT_SPEECH_VOICE,
                instructions=DEFAULT_SPEECH_INSTRUCTIONS, speed=DEFAULT_SPEECH_SPEED)
PHRASE = fixed_speech_phrases()[0]


def audio_bytes(sample_rate=24000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x01\x00" * 12000)
    return buffer.getvalue()


class Response:
    def __init__(self, fail=False):
        self.audio = audio_bytes()
        self.fail = fail
        self.sizes = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def stream_to_file(self, output):
        output.write_bytes(self.audio)

    def iter_bytes(self, chunk_size):
        self.sizes.append(chunk_size)
        for offset in range(0, len(self.audio), chunk_size):
            yield self.audio[offset:offset + chunk_size]
            if self.fail:
                raise RuntimeError("synthetic failure")


def fake_client(response=None):
    response = response or Response()
    create = Mock(return_value=response)
    return SimpleNamespace(audio=SimpleNamespace(speech=SimpleNamespace(
        with_streaming_response=SimpleNamespace(create=create)))), create


@pytest.mark.parametrize("stream", [False, True])
def test_new_synthesizer_uses_prepared_audio_without_api(tmp_path, stream):
    audio = audio_bytes()
    FixedSpeechCache(tmp_path / "cache").save(PHRASE, audio, **SETTINGS)
    client, create = fake_client()
    # A fresh instance represents a new process with no in-memory cache.
    synth = OpenAISpeechSynthesizer(client=client, fixed_cache_dir=tmp_path / "cache")
    output = tmp_path / "reply.wav"
    if stream:
        assert b"".join(synth.stream(PHRASE, output)) == audio
    else:
        synth.synthesize(PHRASE, output)
    assert output.read_bytes() == audio
    assert synth.last_cache_source == "fixed"
    assert synth.last_cache_hit
    synth.synthesize(PHRASE, output)
    assert synth.last_cache_source == "memory"
    create.assert_not_called()


@pytest.mark.parametrize("key,value", [
    ("model", "another-model"), ("voice", "another-voice"),
    ("instructions", "another-style"), ("speed", 1.1),
])
def test_settings_changes_miss_cache(tmp_path, key, value):
    cache = FixedSpeechCache(tmp_path)
    cache.save(PHRASE, audio_bytes(), **SETTINGS)
    assert cache.load(PHRASE, **{**SETTINGS, key: value}) is None


def test_cache_rejects_unregistered_text_and_does_not_write_runtime_audio(tmp_path):
    cache = FixedSpeechCache(tmp_path / "cache")
    with pytest.raises(ValueError, match="registered"):
        cache.save("private free conversation", audio_bytes(), **SETTINGS)
    assert cache.load("private free conversation", **SETTINGS) is None
    client, create = fake_client()
    synth = OpenAISpeechSynthesizer(client=client, fixed_cache_dir=cache.directory)
    for text in ("private free conversation", PHRASE):
        synth.synthesize(text, tmp_path / "reply.wav")
    assert create.call_count == 2
    assert not cache.directory.exists()


@pytest.mark.parametrize("damage", ["missing", "truncated", "checksum", "key", "oversized", "unreadable"])
def test_cache_damage_falls_back_to_normal_synthesis(tmp_path, damage, monkeypatch):
    cache = FixedSpeechCache(tmp_path / "cache")
    path = cache.save(PHRASE, audio_bytes(), **SETTINGS)
    data = path.read_bytes()
    if damage == "missing":
        path.unlink()
    elif damage == "truncated":
        path.write_bytes(data[:30])
    elif damage == "checksum":
        path.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
    elif damage == "key":
        path.write_bytes(data[:25] + bytes([data[25] ^ 1]) + data[26:])
    elif damage == "oversized":
        path.write_bytes(b"x" * (MAX_FIXED_AUDIO_BYTES + 1000))
    else:
        original = Path.open
        def denied(self, *args, **kwargs):
            if self.suffix == ".speech":
                raise PermissionError("synthetic")
            return original(self, *args, **kwargs)
        monkeypatch.setattr(Path, "open", denied)
    client, create = fake_client()
    synth = OpenAISpeechSynthesizer(client=client, fixed_cache_dir=cache.directory)
    synth.synthesize(PHRASE, tmp_path / "reply.wav")
    assert create.call_count == 1
    assert not synth.last_cache_hit
    assert synth.last_cache_source == "none"


@pytest.mark.parametrize("audio", [b"not a wav", audio_bytes(16000), audio_bytes()[:-2], b"x" * (MAX_FIXED_AUDIO_BYTES + 1)])
def test_invalid_audio_cannot_replace_valid_cache(tmp_path, audio):
    cache = FixedSpeechCache(tmp_path)
    good = audio_bytes()
    cache.save(PHRASE, good, **SETTINGS)
    with pytest.raises(ValueError, match="WAV"):
        cache.save(PHRASE, audio, **SETTINGS)
    assert cache.load(PHRASE, **SETTINGS) == good


def test_failed_atomic_write_preserves_old_audio_and_cleans_temp(tmp_path, monkeypatch):
    cache = FixedSpeechCache(tmp_path)
    cache.save(PHRASE, audio_bytes(), **SETTINGS)
    monkeypatch.setattr("robot.fixed_speech.os.replace", Mock(side_effect=OSError("synthetic")))
    with pytest.raises(OSError):
        cache.save(PHRASE, audio_bytes(), **SETTINGS)
    assert cache.load(PHRASE, **SETTINGS) == audio_bytes()
    assert len(list(tmp_path.iterdir())) == 1


def test_streaming_wav_unknown_lengths_are_supported(tmp_path):
    audio = bytearray(audio_bytes())
    audio[4:8] = b"\xff" * 4
    audio[40:44] = b"\xff" * 4
    cache = FixedSpeechCache(tmp_path)
    cache.save(PHRASE, bytes(audio), **SETTINGS)
    assert cache.load(PHRASE, **SETTINGS) == audio


@pytest.mark.parametrize("size", [2048, 4096, 16384])
def test_chunk_sizes_preserve_all_bytes_and_handle_interrupted_stream(tmp_path, size):
    response = Response()
    client, create = fake_client(response)
    synth = OpenAISpeechSynthesizer(client=client, chunk_bytes=size)
    output = tmp_path / "reply.wav"
    chunks = list(synth.stream(PHRASE, output))
    assert b"".join(chunks) == output.read_bytes() == response.audio
    assert max(map(len, chunks)) == size
    assert response.sizes == [size]
    stream = synth.stream("another phrase", output)
    next(stream)
    stream.close()
    assert not output.exists()
    list(synth.stream("another phrase", output))
    assert create.call_count == 3


def test_failed_stream_is_not_cached(tmp_path):
    response = Response(fail=True)
    client, create = fake_client(response)
    synth = OpenAISpeechSynthesizer(client=client, chunk_bytes=2048)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            list(synth.stream(PHRASE, tmp_path / "reply.wav"))
        assert not (tmp_path / "reply.wav").exists()
    assert create.call_count == 2


@pytest.mark.parametrize("size", [0, -1, 1024, True, 2048.0])
def test_invalid_chunk_size_rejected_before_client_creation(size):
    with pytest.raises(ValueError, match="chunk bytes"):
        OpenAISpeechSynthesizer(chunk_bytes=size)


def test_preparation_list_does_not_create_client_or_files(tmp_path, monkeypatch):
    factory = Mock(side_effect=AssertionError("must not create client"))
    monkeypatch.setattr("robot.fixed_speech_cli.create_synthesizer", factory)
    assert prepare(["--backend", "openai", "--list", "--cache-dir", str(tmp_path / "cache")]) == 0
    assert not list(tmp_path.iterdir())


def test_mock_preparation_never_populates_real_cache(tmp_path):
    assert prepare(["--limit", "1", "--cache-dir", str(tmp_path)]) == 0
    assert list((tmp_path / "mock-preview").glob("*.wav"))
    assert not list(tmp_path.glob("*.speech"))
    assert FixedSpeechCache(tmp_path).load(PHRASE, **SETTINGS) is None


def test_preparation_reuses_valid_cache_and_force_regenerates(tmp_path, monkeypatch):
    client, create = fake_client()
    monkeypatch.setattr("robot.fixed_speech_cli.create_synthesizer",
                        lambda *args, **kwargs: OpenAISpeechSynthesizer(client=client))
    args = ["--backend", "openai", "--limit", "1", "--cache-dir", str(tmp_path)]
    assert prepare(args) == 0
    assert prepare(args) == 0
    assert create.call_count == 1
    assert prepare(args + ["--force"]) == 0
    assert create.call_count == 2


def test_preparation_write_failure_returns_nonzero(tmp_path, monkeypatch):
    client, _ = fake_client()
    monkeypatch.setattr("robot.fixed_speech_cli.create_synthesizer",
                        lambda *args, **kwargs: OpenAISpeechSynthesizer(client=client))
    monkeypatch.setattr("robot.fixed_speech_cli.FixedSpeechCache.save", Mock(side_effect=OSError("synthetic")))
    assert prepare(["--backend", "openai", "--limit", "1", "--cache-dir", str(tmp_path)]) == 1


def test_cli_defaults_and_factory_forward_settings(tmp_path, monkeypatch):
    from robot.speech_cli import build_parser, create_synthesizer
    from robot.conversation_loop_cli import build_parser as loop_parser
    for args in (build_parser().parse_args(["hi"]), loop_parser().parse_args([])):
        assert args.fixed_speech_cache is None
    assert build_parser().parse_args(["hi"]).chunk_bytes == 16384
    assert loop_parser().parse_args([]).speech_chunk_bytes == 16384
    factory = Mock()
    monkeypatch.setattr("robot.speech_cli.OpenAISpeechSynthesizer", factory)
    create_synthesizer("openai", model="model", voice="voice", chunk_bytes=2048, fixed_cache_dir=tmp_path)
    assert factory.call_args.kwargs["chunk_bytes"] == 2048
    assert factory.call_args.kwargs["fixed_cache_dir"] == tmp_path
