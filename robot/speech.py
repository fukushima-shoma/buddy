from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol

from robot.audio import generate_tone


DEFAULT_SPEECH_MODEL = "gpt-4o-mini-tts"
DEFAULT_SPEECH_VOICE = "coral"
DEFAULT_SPEECH_STYLE = "calm"
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
        "3歳くらいの子どもを安心させる、若々しく優しい女性を思わせる声色で、"
        "温かく自然な日本語を話してください。そばで話を聞くやさしい友だちのように、"
        "少しゆっくりした速さと柔らかな声量で、"
        "文の意味に沿った穏やかな抑揚をつけてください。質問の語尾はわずかに上げ、"
        "句読点では短く自然な間を置いてください。ささやき声、大げさなアニメ声、"
        "幼児語を多用する話し方にはしないでください。"
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
