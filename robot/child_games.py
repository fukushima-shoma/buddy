from __future__ import annotations

from dataclasses import dataclass
import unicodedata


@dataclass(frozen=True)
class GameQuestion:
    question: str
    answers: tuple[str, ...]
    answer_name: str


GAME_BANKS = {
    "riddle": (
        GameQuestion(
            "パンはパンでも、食べられないパンはなあに？",
            ("フライパン",),
            "フライパン",
        ),
        GameQuestion(
            "雨の日に、頭の上にさすものはなあに？",
            ("かさ", "傘"),
            "かさ",
        ),
    ),
    "animal": (
        GameQuestion(
            "お鼻が長くて、大きなお耳の動物はなあに？",
            ("ぞう", "象"),
            "ぞう",
        ),
        GameQuestion(
            "にゃーと鳴く動物はなあに？",
            ("ねこ", "猫"),
            "ねこ",
        ),
        GameQuestion(
            "首がとっても長い動物はなあに？",
            ("きりん", "キリン"),
            "きりん",
        ),
    ),
    "vehicle": (
        GameQuestion(
            "線路の上を走る乗り物はなあに？",
            ("でんしゃ", "電車"),
            "でんしゃ",
        ),
        GameQuestion(
            "空を飛ぶ乗り物はなあに？",
            ("ひこうき", "飛行機"),
            "ひこうき",
        ),
        GameQuestion(
            "火事のときに来る、赤い車はなあに？",
            ("しょうぼうしゃ", "消防車"),
            "しょうぼうしゃ",
        ),
    ),
}

START_COMMANDS = {
    "なぞなぞしよう": ("riddle", "なぞなぞを始めるね。"),
    "なぞなぞやろう": ("riddle", "なぞなぞを始めるね。"),
    "どうぶつクイズ": ("animal", "どうぶつクイズを始めるね。"),
    "動物クイズ": ("animal", "どうぶつクイズを始めるね。"),
    "のりものクイズ": ("vehicle", "のりものクイズを始めるね。"),
    "乗り物クイズ": ("vehicle", "のりものクイズを始めるね。"),
}
REPEAT_COMMANDS = frozenset({"もう一回", "もういっかい"})
END_COMMANDS = frozenset({"おしまい", "ゲームおしまい", "クイズおしまい"})


def normalize_game_text(text: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", text).casefold()
        if character.isalnum()
    )


def is_game_end_transcript(text: str) -> bool:
    return normalize_game_text(text) in END_COMMANDS


class ChildGameController:
    def __init__(self) -> None:
        self._mode: str | None = None
        self._index = 0

    @property
    def active(self) -> bool:
        return self._mode is not None

    def handle(self, text: str) -> str | None:
        normalized = normalize_game_text(text)
        start = START_COMMANDS.get(normalized)
        if start is not None:
            self._mode, introduction = start
            self._index = 0
            return f"{introduction}{self._current.question}"
        if self._mode is None:
            return None
        if normalized in END_COMMANDS:
            self._mode = None
            self._index = 0
            return "ゲームはおしまい。また遊ぼうね。"
        if normalized in REPEAT_COMMANDS:
            return f"もう一回言うね。{self._current.question}"

        current = self._current
        correct = any(
            normalize_game_text(answer) in normalized
            for answer in current.answers
        )
        feedback = (
            f"せいかい！{current.answer_name}だよ。"
            if correct
            else f"おしい！答えは、{current.answer_name}だよ。"
        )
        self._index = (self._index + 1) % len(GAME_BANKS[self._mode])
        return f"{feedback}次は、{self._current.question}"

    @property
    def _current(self) -> GameQuestion:
        if self._mode is None:
            raise RuntimeError("No child game is active.")
        return GAME_BANKS[self._mode][self._index]
