from __future__ import annotations

import re
import unicodedata

from robot.profile_memory import ParentManagedMemory


PROFILE_LABELS = {
    "好きな色": "色",
    "好きな動物": "動物",
    "好きな食べ物": "食べ物",
}
_SUBJECT = r"(?:(?:ぼく|僕|わたし|私)の)?"


def _compact(text: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", text)
        if character.isalnum()
    )


class SpokenProfileMemory:
    """Handle a small allowlist of profile facts without external services."""

    def __init__(self, memory: ParentManagedMemory) -> None:
        self.memory = memory

    def handle(self, transcript: str) -> str | None:
        compact = _compact(transcript)
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
                for suffix in ("だよ", "です"):
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
