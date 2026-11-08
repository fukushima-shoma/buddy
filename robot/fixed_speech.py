"""Allowlisted, pre-generated speech. Runtime callers only read this cache."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import wave

from robot import conversation_intents as intents
from robot.buddy_identity import BUDDY_PROACTIVE_INVITATION

DEFAULT_FIXED_SPEECH_CACHE = Path("captures/audio/fixed-speech-cache")
MAX_FIXED_AUDIO_BYTES = 4 * 1024 * 1024
_MAGIC = b"BUDDY-FIXED-SPEECH-1\n"
_HEADER_SIZE = len(_MAGIC) + 64


def fixed_speech_phrases() -> tuple[str, ...]:
    """Explicitly selected constants only; never accept dynamic conversation text."""
    return tuple(dict.fromkeys([
        *(text for choices in intents.LOCAL_SHORT_REPLIES.values() for text in choices),
        *intents.CHILD_RETRY_REPLIES, *intents.DEFAULT_RETRY_REPLIES,
        intents.DEFAULT_FAREWELL_REPLY, intents.DEFAULT_INACTIVITY_REPLY,
        BUDDY_PROACTIVE_INVITATION,
        intents.MOBILITY_START_REPLY, intents.MOBILITY_CONFIRM_REPLY,
        intents.MOBILITY_CONFIRM_AGAIN_REPLY, intents.MOBILITY_CANCEL_REPLY,
        intents.MOBILITY_CLARIFY_REPLY, intents.MOBILITY_ALREADY_RUNNING_REPLY,
        intents.MOBILITY_STOP_REPLY, intents.MOBILITY_ALREADY_STOPPED_REPLY,
        intents.MOBILITY_FAREWELL_REPLY, intents.MOBILITY_UNAVAILABLE_REPLY,
    ]))


def _valid_wav(audio: bytes) -> bool:
    if not 0 < len(audio) <= MAX_FIXED_AUDIO_BYTES:
        return False
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav:
            width = wav.getnchannels() * wav.getsampwidth()
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 24000:
                return False
            frames = wav.readframes(MAX_FIXED_AUDIO_BYTES // width + 1)
            # Streaming WAV may use an unknown-length data chunk (0xffffffff).
            declared = wav.getnframes() * width
            return bool(frames) and len(frames) % width == 0 and (
                len(frames) == declared or declared >= 0xfffffffe
            )
    except (wave.Error, EOFError, ValueError):
        return False


class FixedSpeechCache:
    def __init__(self, directory: Path) -> None:
        self.directory = directory.expanduser()
        self._allowed = frozenset(fixed_speech_phrases())

    def _key(self, text: str, model: str, voice: str, instructions: str, speed: float) -> bytes:
        settings = [1, "openai-speech", "wav", model, voice, instructions, float(speed), text]
        return hashlib.sha256(json.dumps(settings, ensure_ascii=False).encode()).digest()

    def load(self, text: str, *, model: str, voice: str, instructions: str, speed: float) -> bytes | None:
        if text not in self._allowed:
            return None
        key = self._key(text, model, voice, instructions, speed)
        try:
            with (self.directory / (key.hex() + ".speech")).open("rb") as source:
                payload = source.read(_HEADER_SIZE + MAX_FIXED_AUDIO_BYTES + 1)
            audio = payload[_HEADER_SIZE:]
            if (payload[:len(_MAGIC)] == _MAGIC
                    and payload[len(_MAGIC):len(_MAGIC) + 32] == key
                    and payload[len(_MAGIC) + 32:_HEADER_SIZE] == hashlib.sha256(audio).digest()
                    and _valid_wav(audio)):
                return audio
        except OSError:
            pass
        return None

    def save(self, text: str, audio: bytes, *, model: str, voice: str, instructions: str, speed: float) -> Path:
        """Only the explicit preparation command writes; failures preserve old files."""
        if text not in self._allowed:
            raise ValueError("Only registered fixed phrases may be persisted.")
        if not _valid_wav(audio):
            raise ValueError("Expected a complete mono 24kHz PCM16 WAV within the size limit.")
        key = self._key(text, model, voice, instructions, speed)
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / (key.hex() + ".speech")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.directory, delete=False) as output:
                temporary = Path(output.name)
                output.write(_MAGIC + key + hashlib.sha256(audio).digest() + audio)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return target
