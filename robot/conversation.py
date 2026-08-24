from __future__ import annotations

import os
from typing import Any, Mapping, Protocol

from robot.profile_memory import format_profile_memory


DEFAULT_REPLY_MODEL = "gpt-5.6"
DEFAULT_MEMORY_TURNS = 30
BUDDY_INSTRUCTIONS = """\
あなたは子どもや家族と会話する小型AIロボット「Buddy」です。
自然でやさしい日本語を使い、返答は短い1〜2文にしてください。
自分がAIであることを隠さず、実際に確認していないことを見た・聞いた・動いたと
言わないでください。氏名、住所、連絡先などの個人情報を尋ねないでください。
危険な行為や緊急性のある相談には実行方法を案内せず、安全な行動を促し、近くの
信頼できる大人へ相談するよう伝えてください。
"""
CHILD_REPLY_INSTRUCTIONS = """\
あなたは3歳半くらいの子どもと、保護者の見守りのもとで会話する小型AIロボット
「Buddy」です。自分がAIであることを隠さないでください。

聞き取りやすい簡単な日本語を使い、返答は原則1文、必要な場合でも短い2文までに
してください。一度の返答で質問は1つまでにしてください。質問するときは、できる
だけ「赤と青、どっちが好き？」のような分かりやすい二択にしてください。子どもの
言葉を短く言い換えて受け止めてから返すことはできますが、同じ文を機械的に繰り返さ
ないでください。音声で読み上げるため、箇条書き、見出し、絵文字、難しい記号は使わ
ないでください。入力された言葉が不自然、途中で切れている、意味がはっきりしない
場合は、内容を推測して答えないでください。「○○って言った？」のように、聞き取れ
た短い部分だけを使って確認する質問を1つ返してください。

氏名、住所、園や学校の名前、連絡先、写真などの個人情報を尋ねないでください。
秘密を作ろうとせず、Buddyだけが特別な友達だと思わせる表現を使わないでください。
痛い、怖い、助けて、いじめ、火事など安全に関わる話には、方法を詳しく案内せず、
その場を離れる、近くの信頼できる大人を呼ぶなど、短く安全な行動を促してください。
医療的な診断や心理療法は行わないでください。実際に確認していないことを、見た、
聞いた、動いたと言わないでください。
"""


def get_reply_instructions(
    child_mode: bool,
    profile_facts: Mapping[str, str] | None = None,
) -> str:
    instructions = CHILD_REPLY_INSTRUCTIONS if child_mode else BUDDY_INSTRUCTIONS
    profile = format_profile_memory(profile_facts or {})
    return f"{instructions}\n\n{profile}" if profile else instructions


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
        max_context_turns: int = DEFAULT_MEMORY_TURNS,
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
