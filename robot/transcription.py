from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol


DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"


class Transcriber(Protocol):
    def transcribe(self, source: Path, *, language: str = "ja") -> str:
        """Return the text spoken in an audio file."""


class MockTranscriber:
    def __init__(self, text: str = "こんにちは、Buddy") -> None:
        self.text = text
        self.sources: list[Path] = []

    def transcribe(self, source: Path, *, language: str = "ja") -> str:
        self.sources.append(source.expanduser())
        return self.text


class OpenAITranscriber:
    def __init__(
        self,
        model: str = DEFAULT_TRANSCRIPTION_MODEL,
        client: Any | None = None,
    ) -> None:
        if client is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise RuntimeError(
                    "OPENAI_API_KEY is not set. Set it in the shell before using "
                    "the OpenAI transcription backend."
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
        self._client = client

    def transcribe(self, source: Path, *, language: str = "ja") -> str:
        source = source.expanduser()
        with source.open("rb") as audio_file:
            response = self._client.audio.transcriptions.create(
                model=self.model,
                file=audio_file,
                language=language,
            )
        text = getattr(response, "text", None)
        if text is None and isinstance(response, dict):
            text = response.get("text")
        if not isinstance(text, str):
            raise RuntimeError("The transcription response did not contain text.")
        return text.strip()
