from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol

from robot.audio import generate_tone


DEFAULT_SPEECH_MODEL = "gpt-4o-mini-tts"
DEFAULT_SPEECH_VOICE = "marin"
DEFAULT_SPEECH_INSTRUCTIONS = (
    "自然で明るく、子どもに話しかけるような、やさしい日本語で話してください。"
)


class SpeechSynthesizer(Protocol):
    def synthesize(self, text: str, output: Path) -> Path:
        """Generate a WAV file containing spoken text."""


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
        client: Any | None = None,
    ) -> None:
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
        self._client = client

    def synthesize(self, text: str, output: Path) -> Path:
        if not text.strip():
            raise ValueError("Cannot synthesize empty text.")
        output = output.expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        with self._client.audio.speech.with_streaming_response.create(
            model=self.model,
            voice=self.voice,
            input=text,
            instructions=self.instructions,
            response_format="wav",
        ) as response:
            response.stream_to_file(output)
        return output
