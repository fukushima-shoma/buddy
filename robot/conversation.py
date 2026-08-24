from __future__ import annotations

import os
from typing import Any, Protocol


DEFAULT_REPLY_MODEL = "gpt-5.6"
BUDDY_INSTRUCTIONS = """\
あなたは子どもや家族と会話する小型AIロボット「Buddy」です。
自然でやさしい日本語を使い、返答は短い1〜2文にしてください。
自分がAIであることを隠さず、実際に確認していないことを見た・聞いた・動いたと
言わないでください。氏名、住所、連絡先などの個人情報を尋ねないでください。
危険な行為や緊急性のある相談には実行方法を案内せず、安全な行動を促し、近くの
信頼できる大人へ相談するよう伝えてください。
"""


class ReplyGenerator(Protocol):
    def reply(self, user_text: str) -> str:
        """Generate one short reply to recognized speech."""


class MockReplyGenerator:
    def __init__(self, reply_text: str = "こんにちは！今日は何をして遊ぶ？") -> None:
        self.reply_text = reply_text
        self.inputs: list[str] = []

    def reply(self, user_text: str) -> str:
        self.inputs.append(user_text)
        return self.reply_text


class OpenAIReplyGenerator:
    def __init__(
        self,
        model: str = DEFAULT_REPLY_MODEL,
        instructions: str = BUDDY_INSTRUCTIONS,
        client: Any | None = None,
    ) -> None:
        if client is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise RuntimeError(
                    "OPENAI_API_KEY is not set. Set it in the shell before using "
                    "the OpenAI reply backend."
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
        self.instructions = instructions
        self._client = client

    def reply(self, user_text: str) -> str:
        if not user_text.strip():
            raise ValueError("Cannot generate a reply from empty text.")
        response = self._client.responses.create(
            model=self.model,
            reasoning={"effort": "low"},
            instructions=self.instructions,
            input=user_text,
        )
        text = getattr(response, "output_text", None)
        if not isinstance(text, str):
            raise RuntimeError("The response did not contain output text.")
        return text.strip()
