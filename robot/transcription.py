from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any, Protocol


DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"
CHILD_TRANSCRIPTION_PROMPT = (
    "3歳半くらいの子どもと小型ロボットBuddyの、短い日本語の日常会話です。"
    "子どもの発音は不明瞭な場合があります。よく出る話題は、遊び、動物、色、"
    "食べ物、乗り物、家族、あいさつです。Buddy、赤、青、黄色、犬、猫、車、"
    "電車などの短い言葉が使われます。"
)
_UNRELIABLE_TRANSCRIPTION_PHRASES = (
    "ご視聴ありがとうございました",
    "チャンネル登録",
    "字幕をご覧",
    "字幕提供",
)


def is_unreliable_child_transcript(text: str) -> bool:
    compact = "".join(text.split())
    if not compact:
        return True
    if len(compact) > 80:
        return True
    if any(phrase in compact for phrase in _UNRELIABLE_TRANSCRIPTION_PHRASES):
        return True
    return re.search(r"[ぁ-んァ-ヶ一-龠A-Za-z0-9]", compact) is None


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
        prompt: str | None = None,
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
        self.prompt = prompt
        self._client = client

    def transcribe(self, source: Path, *, language: str = "ja") -> str:
        source = source.expanduser()
        with source.open("rb") as audio_file:
            request: dict[str, object] = dict(
                model=self.model,
                file=audio_file,
                language=language,
            )
            if self.prompt:
                request["prompt"] = self.prompt
            response = self._client.audio.transcriptions.create(**request)
        text = getattr(response, "text", None)
        if text is None and isinstance(response, dict):
            text = response.get("text")
        if not isinstance(text, str):
            raise RuntimeError("The transcription response did not contain text.")
        return text.strip()
