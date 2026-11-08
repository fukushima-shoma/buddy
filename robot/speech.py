from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterator
import os
from pathlib import Path
from typing import Any, Protocol

from robot.audio import generate_tone
from robot.fixed_speech import FixedSpeechCache


DEFAULT_SPEECH_MODEL = "gpt-4o-mini-tts"
DEFAULT_SPEECH_VOICE = "coral"
DEFAULT_SPEECH_STYLE = "calm"
DEFAULT_SPEECH_SPEED = 0.95
MAX_AUDIO_CACHE_ENTRIES = 32
MAX_AUDIO_CACHE_BYTES = 4 * 1024 * 1024
SPEECH_CHUNK_SIZES = (2048, 4096, 16384)
DEFAULT_SPEECH_CHUNK_BYTES = 16384
SPEECH_STYLE_INSTRUCTIONS = {
    "buddy": (
        "3歳くらいの子どもへ話すような、親しみのある自然な日本語で話してください。"
        "少しゆっくり、柔らかく温かい声にしてください。単語を一語ずつ区切らず、"
        "文章の意味に合わせて自然な抑揚をつけてください。質問の語尾は少し上げ、"
        "嬉しい内容では控えめに明るくしてください。句読点では短く自然な間を置いて"
        "ください。大げさなアニメ声や、幼児語を多用する話し方にはしないでください。"
    ),
    "cheerful": (
        "子どもに話しかける、明るく親しみのある自然な日本語で話してください。"
        "普段より少し弾む声色にし、嬉しい言葉を自然に強調してください。話す速さは"
        "少しゆっくりに保ち、大げさに叫んだり、アニメ声にしたりしないでください。"
    ),
    "calm": (
        "幼さのある中性的な声色で、3歳くらいの子どもが身構えずリラックスできる、"
        "温かく自然な日本語を話してください。年上の大人が読み聞かせる声ではなく、"
        "少し年上の子どもの友だちが、そばで穏やかに話すような声にしてください。"
        "少しゆっくりした速さと柔らかな声量を保ち、文の意味に沿った自然な抑揚を"
        "つけてください。質問の語尾はわずかに上げ、"
        "発見や遊びの場面では少し弾む抑揚を加え、内容に合わせて声の表情を変えてください。"
        "句読点では短く自然な間を置いてください。甲高い声、赤ちゃん言葉、ささやき声、"
        "大げさなアニメ声にはしないでください。"
    ),
}
SPEECH_STYLES = tuple(SPEECH_STYLE_INSTRUCTIONS)
DEFAULT_SPEECH_INSTRUCTIONS = SPEECH_STYLE_INSTRUCTIONS[DEFAULT_SPEECH_STYLE]


def get_speech_instructions(style: str) -> str:
    try:
        return SPEECH_STYLE_INSTRUCTIONS[style]
    except KeyError as exc:
        choices = ", ".join(SPEECH_STYLES)
        raise ValueError(
            f"Unsupported speech style: {style}. Choose from: {choices}."
        ) from exc


class SpeechSynthesizer(Protocol):
    def synthesize(self, text: str, output: Path) -> Path:
        """Generate a WAV file containing spoken text."""


class StreamingSpeechSynthesizer(Protocol):
    def stream(self, text: str, output: Path) -> Iterator[bytes]:
        """Yield WAV bytes while saving the complete response for later reuse."""


class MockSpeechSynthesizer:
    def __init__(self) -> None:
        self.inputs: list[str] = []
        self.outputs: list[Path] = []

    def synthesize(self, text: str, output: Path) -> Path:
        if not text.strip():
            raise ValueError("Cannot synthesize empty text.")
        output = output.expanduser()
        self.inputs.append(text)
        self.outputs.append(output)
        return generate_tone(output, duration=0.1, volume=0.0)


class OpenAISpeechSynthesizer:
    def __init__(
        self,
        model: str = DEFAULT_SPEECH_MODEL,
        voice: str = DEFAULT_SPEECH_VOICE,
        instructions: str = DEFAULT_SPEECH_INSTRUCTIONS,
        speed: float = DEFAULT_SPEECH_SPEED,
        client: Any | None = None,
        chunk_bytes: int = DEFAULT_SPEECH_CHUNK_BYTES,
        fixed_cache_dir: Path | None = None,
    ) -> None:
        if not 0.25 <= speed <= 4.0:
            raise ValueError("Speech speed must be between 0.25 and 4.0.")
        if type(chunk_bytes) is not int or chunk_bytes not in SPEECH_CHUNK_SIZES:
            raise ValueError("Speech chunk bytes must be 2048, 4096, or 16384.")
        if client is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise RuntimeError(
                    "OPENAI_API_KEY is not set. Set it in the shell before using "
                    "the OpenAI speech backend."
                )
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "The OpenAI SDK is required. Activate .venv and run: "
                    "python -m pip install -r requirements-phase3.txt"
                ) from exc
            client = OpenAI()
        self.model = model
        self.voice = voice
        self.instructions = instructions
        self.speed = speed
        self._client = client
        self.chunk_bytes = chunk_bytes
        self._fixed_cache = FixedSpeechCache(fixed_cache_dir) if fixed_cache_dir is not None else None
        # Runtime generation only populates this bounded process-local cache.
        self._audio_cache: OrderedDict[
            tuple[str, str, str, float, str], bytes
        ] = OrderedDict()
        self._cache_bytes = 0
        self.last_cache_hit = False
        self.last_cache_source = "none"

    def _cached_audio(self, text: str) -> bytes | None:
        key = (self.model, self.voice, self.instructions, self.speed, text)
        cached = self._audio_cache.get(key)
        self.last_cache_source = "none"
        if cached is not None:
            self._audio_cache.move_to_end(key)
            self.last_cache_source = "memory"
        elif self._fixed_cache is not None:
            cached = self._fixed_cache.load(text, model=self.model, voice=self.voice,
                                           instructions=self.instructions, speed=self.speed)
            if cached is not None:
                self.last_cache_source = "fixed"
                self._cache_audio(key, cached)
        self.last_cache_hit = cached is not None
        return cached

    def _cache_audio(
        self,
        key: tuple[str, str, str, float, str],
        audio: bytes,
    ) -> None:
        if not 0 < len(audio) <= MAX_AUDIO_CACHE_BYTES:
            return
        while self._audio_cache and (
            len(self._audio_cache) >= MAX_AUDIO_CACHE_ENTRIES
            or self._cache_bytes + len(audio) > MAX_AUDIO_CACHE_BYTES
        ):
            _, evicted = self._audio_cache.popitem(last=False)
            self._cache_bytes -= len(evicted)
        self._audio_cache[key] = audio
        self._cache_bytes += len(audio)

    def synthesize(self, text: str, output: Path) -> Path:
        if not text.strip():
            raise ValueError("Cannot synthesize empty text.")
        output = output.expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        key = (self.model, self.voice, self.instructions, self.speed, text)
        cached = self._cached_audio(text)
        if cached is not None:
            self.last_cache_hit = True
            output.write_bytes(cached)
            self._audio_cache.move_to_end(key)
            return output
        self.last_cache_hit = False
        with self._client.audio.speech.with_streaming_response.create(
            model=self.model,
            voice=self.voice,
            input=text,
            instructions=self.instructions,
            response_format="wav",
            speed=self.speed,
        ) as response:
            response.stream_to_file(output)
        self._cache_audio(key, output.read_bytes())
        return output

    def stream(self, text: str, output: Path) -> Iterator[bytes]:
        if not text.strip():
            raise ValueError("Cannot synthesize empty text.")
        output = output.expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        key = (self.model, self.voice, self.instructions, self.speed, text)
        cached = self._cached_audio(text)
        if cached is not None:
            self.last_cache_hit = True
            output.write_bytes(cached)
            self._audio_cache.move_to_end(key)
            yield cached
            return

        self.last_cache_hit = False
        audio = bytearray()
        completed = False
        try:
            with self._client.audio.speech.with_streaming_response.create(
                model=self.model,
                voice=self.voice,
                input=text,
                instructions=self.instructions,
                response_format="wav",
                speed=self.speed,
            ) as response:
                with output.open("wb") as output_file:
                    for chunk in response.iter_bytes(chunk_size=self.chunk_bytes):
                        if not chunk:
                            continue
                        output_file.write(chunk)
                        if len(audio) <= MAX_AUDIO_CACHE_BYTES:
                            audio.extend(chunk)
                        yield chunk
            completed = True
        finally:
            if not completed:
                output.unlink(missing_ok=True)
        self._cache_audio(key, bytes(audio))
