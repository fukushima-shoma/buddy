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
        remember_context: bool = False,
        max_context_turns: int = 6,
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
        self.remember_context = remember_context
        self.max_context_turns = max(1, max_context_turns)
        self._previous_response_id: str | None = None
        self._context_turns = 0
        self._client = client

    def reply(self, user_text: str) -> str:
        if not user_text.strip():
            raise ValueError("Cannot generate a reply from empty text.")
        if self.remember_context and self._context_turns >= self.max_context_turns:
            self.reset_context()
        request = dict(
            model=self.model,
            reasoning={"effort": "low"},
            instructions=self.instructions,
            input=user_text,
        )
        if self.remember_context and self._previous_response_id is not None:
            request["previous_response_id"] = self._previous_response_id
        response = self._client.responses.create(**request)
        text = getattr(response, "output_text", None)
        if not isinstance(text, str):
            raise RuntimeError("The response did not contain output text.")
        if self.remember_context:
            response_id = getattr(response, "id", None)
            if not isinstance(response_id, str) or not response_id:
                raise RuntimeError("The response did not contain an ID for context.")
            self._previous_response_id = response_id
            self._context_turns += 1
        return text.strip()

    def reset_context(self) -> None:
        self._previous_response_id = None
        self._context_turns = 0
