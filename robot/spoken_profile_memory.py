from __future__ import annotations

from datetime import date
import re
import unicodedata

from robot.profile_memory import ParentManagedMemory


PROFILE_LABELS = {
    "好きな色": "色",
    "好きな動物": "動物",
    "好きな食べ物": "食べ物",
}
BIRTHDAY_KEY = "誕生日"
_SUBJECT = r"(?:(?:ぼく|僕|わたし|私)の)?"


def _compact(text: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", text)
        if character.isalnum()
    )


def normalize_birthday(value: str) -> str | None:
    match = re.fullmatch(r"(\d{1,2})月(\d{1,2})日", value)
    if match is None:
        return None
    month, day = (int(part) for part in match.groups())
    try:
        date(2000, month, day)
    except ValueError:
        return None
    return f"{month}月{day}日"


class SpokenProfileMemory:
    """Handle a small allowlist of profile facts without external services."""

    def __init__(self, memory: ParentManagedMemory) -> None:
        self.memory = memory

    def handle(self, transcript: str) -> str | None:
        compact = _compact(transcript)
        birthday_reply = self._handle_birthday(compact)
        if birthday_reply is not None:
            return birthday_reply
        for key, label in PROFILE_LABELS.items():
            if compact in {
                f"{key}は何",
                f"{key}覚えてる",
                f"{key}を覚えてる",
            }:
                value = self.memory.load().get(key)
                if value is None:
                    return f"{key}は、まだ覚えていないよ。"
                return f"{key}は、{value}だよ。"

            if compact in {f"{key}を忘れて", f"{key}忘れて"}:
                removed = self.memory.delete(key)
                if removed:
                    return f"{key}は忘れたよ。"
                return f"{key}は、まだ覚えていないよ。"

            match = re.fullmatch(
                rf"{_SUBJECT}{key}は(.{{1,24}})",
                compact,
            )
            if match is not None:
                value = match.group(1)
                for suffix in ("って覚えて", "だよ", "です"):
                    if value.endswith(suffix):
                        value = value[: -len(suffix)]
                        break
                if not value or len(value) > 20:
                    continue
                if value in {"何", "なに"}:
                    continue
                self.memory.set(key, value)
                return f"好きな{label}は、{value}って覚えたよ。"
        return None

    def _handle_birthday(self, compact: str) -> str | None:
        if compact in {
            "誕生日は何",
            "誕生日はいつ",
            "誕生日覚えてる",
            "誕生日を覚えてる",
        }:
            value = self.memory.load().get(BIRTHDAY_KEY)
            if value is None:
                return "誕生日は、まだ覚えていないよ。"
            return f"誕生日は、{value}だよ。"

        if compact in {"誕生日を忘れて", "誕生日忘れて"}:
            removed = self.memory.delete(BIRTHDAY_KEY)
            if removed:
                return "誕生日は忘れたよ。"
            return "誕生日は、まだ覚えていないよ。"

        match = re.fullmatch(rf"{_SUBJECT}誕生日は(.{{1,24}})", compact)
        if match is None:
            return None
        value = match.group(1)
        for suffix in ("って覚えて", "だよ", "です"):
            if value.endswith(suffix):
                value = value[: -len(suffix)]
                break
        if value in {"何", "なに", "いつ"}:
            return None
        birthday = normalize_birthday(value)
        if birthday is None:
            return "誕生日は、何月何日かを教えてね。"
        self.memory.set(BIRTHDAY_KEY, birthday)
        return f"誕生日は、{birthday}って覚えたよ。"
