from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from robot.conversation_memory import sanitize_conversation_text


DEFAULT_SHARED_EXPERIENCE_PATH = Path("data/shared-experiences.json")
MAX_SHARED_EXPERIENCES = 500
MAX_EXPERIENCE_LENGTH = 80
_SENSITIVE_WORDS = (
    "住所",
    "連絡先",
    "電話番号",
    "メールアドレス",
    "幼稚園",
    "保育園",
    "こども園",
    "小学校",
    "中学校",
    "高校",
    "丁目",
    "番地",
    "誕生日",
)


def clean_experience_summary(summary: str) -> str:
    cleaned = " ".join(summary.strip(" 「」『』\"'").split())
    if len(cleaned) < 2:
        raise ValueError("Shared experience must be at least 2 characters.")
    if len(cleaned) > MAX_EXPERIENCE_LENGTH:
        raise ValueError(
            f"Shared experience must be {MAX_EXPERIENCE_LENGTH} characters or fewer."
        )
    sanitized = sanitize_conversation_text(cleaned)
    if sanitized != cleaned or any(word in cleaned for word in _SENSITIVE_WORDS):
        raise ValueError("Shared experience may contain personal information.")
    return cleaned


def _compact(text: str) -> str:
    return "".join(character for character in text.casefold() if character.isalnum())


def _bigrams(text: str) -> set[str]:
    return {text[index : index + 2] for index in range(max(0, len(text) - 1))}


class SharedExperienceStore:
    """Keep short, explicit shared memories locally until they are deleted."""

    def __init__(self, path: Path = DEFAULT_SHARED_EXPERIENCE_PATH) -> None:
        self.path = path.expanduser()

    def load(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        try:
            payload: Any = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Could not read shared experience memory: {self.path}"
            ) from exc
        entries = payload.get("experiences") if isinstance(payload, dict) else None
        required = {"id", "created_at", "summary"}
        if not isinstance(entries, list) or not all(
            isinstance(entry, dict)
            and required.issubset(entry)
            and all(isinstance(entry[key], str) for key in required)
            for entry in entries
        ):
            raise RuntimeError(f"Invalid shared experience memory: {self.path}")
        return [{key: entry[key] for key in required} for entry in entries]

    def remember(self, summary: str) -> dict[str, str]:
        summary = clean_experience_summary(summary)
        entries = self.load()
        compact = _compact(summary)
        for entry in entries:
            if _compact(entry["summary"]) == compact:
                return entry
        if len(entries) >= MAX_SHARED_EXPERIENCES:
            raise ValueError(
                "Shared experience memory is full; delete an entry before adding one."
            )
        entry = {
            "id": uuid4().hex,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
        }
        entries.append(entry)
        self._save(entries)
        return entry

    def relevant(self, query: str, limit: int = 8) -> list[dict[str, str]]:
        if limit <= 0:
            return []
        entries = self.load()
        compact_query = _compact(query)
        query_bigrams = _bigrams(compact_query)
        ranked: list[tuple[int, int, dict[str, str]]] = []
        for index, entry in enumerate(entries):
            compact_summary = _compact(entry["summary"])
            overlap = len(query_bigrams & _bigrams(compact_summary))
            contained = int(
                bool(compact_query)
                and (
                    compact_query in compact_summary
                    or compact_summary in compact_query
                )
            )
            ranked.append((contained * 100 + overlap, index, entry))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [entry for score, _, entry in ranked if score > 0][:limit]

    def recent(self, limit: int = 20) -> list[dict[str, str]]:
        if limit <= 0:
            return []
        return self.load()[-limit:]

    def delete(self, experience_id: str) -> bool:
        entries = self.load()
        retained = [entry for entry in entries if entry["id"] != experience_id]
        if len(retained) == len(entries):
            return False
        self._save(retained)
        return True

    def forget_summary(self, summary: str) -> bool:
        compact = _compact(clean_experience_summary(summary))
        entries = self.load()
        retained = [
            entry for entry in entries if _compact(entry["summary"]) != compact
        ]
        if len(retained) == len(entries):
            return False
        self._save(retained)
        return True

    def clear(self) -> None:
        self._save([])

    def _save(self, entries: list[dict[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {"version": 1, "experiences": entries},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        temporary.replace(self.path)


_REMEMBER_PATTERNS = (
    re.compile(r"^(?P<summary>.+?)(?:という|って)?ことを覚えて(?:おいて)?[。.!！?？]*$"),
    re.compile(r"^(?P<summary>.+?)って覚えて(?:おいて)?[。.!！?？]*$"),
)
_FORGET_PATTERN = re.compile(
    r"^(?P<summary>.+?)(?:という|って)?ことを忘れて[。.!！?？]*$"
)
_LIST_PHRASES = frozenset(
    {
        "何を覚えてる",
        "なにを覚えてる",
        "思い出を教えて",
        "覚えてることを教えて",
    }
)


class SpokenSharedExperienceMemory:
    """Handle explicit remember, recall, and forget requests without an API call."""

    def __init__(self, store: SharedExperienceStore) -> None:
        self.store = store

    def handle(self, transcript: str) -> str | None:
        text = transcript.strip()
        compact = _compact(text)
        if compact in {_compact(phrase) for phrase in _LIST_PHRASES}:
            try:
                memories = self.store.recent(3)
            except RuntimeError:
                return "ごめんね、今は思い出を確認できないよ。"
            if not memories:
                return "いっしょの思い出は、まだ覚えていないよ。"
            summaries = "、".join(entry["summary"] for entry in memories)
            return f"覚えているのは、{summaries}だよ。"

        forget = _FORGET_PATTERN.fullmatch(text)
        if forget is not None:
            summary = forget.group("summary")
            try:
                removed = self.store.forget_summary(summary)
            except (RuntimeError, ValueError):
                return "その思い出は、うまく確認できなかったよ。"
            if removed:
                return f"「{summary}」の思い出は忘れたよ。"
            return "その思い出は、まだ覚えていないよ。"

        for pattern in _REMEMBER_PATTERNS:
            match = pattern.fullmatch(text)
            if match is None:
                continue
            summary = match.group("summary")
            try:
                entry = self.store.remember(summary)
            except ValueError:
                return "それは思い出として保存できないよ。近くの大人と確認してね。"
            except RuntimeError:
                return "ごめんね、今は思い出を保存できないよ。"
            return f"うん。「{entry['summary']}」を、いっしょの思い出として覚えたよ。"
        return None
