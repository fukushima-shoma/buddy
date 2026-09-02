from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


DEFAULT_CONVERSATION_MEMORY_PATH = Path("data/conversation-memory.json")
DEFAULT_CONVERSATION_MEMORY_LIMIT = 100
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+81[- ]?|0)\d{1,4}[- ]?\d{1,4}[- ]?\d{3,4}(?!\d)"
)


def sanitize_conversation_text(text: str) -> str:
    normalized = " ".join(text.split())
    normalized = _EMAIL_PATTERN.sub("[メールアドレス削除]", normalized)
    normalized = _PHONE_PATTERN.sub("[電話番号削除]", normalized)
    return normalized[:500]


class ConversationMemoryStore:
    def __init__(
        self,
        path: Path = DEFAULT_CONVERSATION_MEMORY_PATH,
        *,
        max_entries: int = DEFAULT_CONVERSATION_MEMORY_LIMIT,
    ) -> None:
        self.path = path.expanduser()
        self.max_entries = max(1, max_entries)

    def load(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        try:
            payload: Any = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Could not read conversation memory: {self.path}") from exc
        entries = payload.get("entries") if isinstance(payload, dict) else None
        required = {"timestamp", "session", "user", "assistant"}
        if not isinstance(entries, list) or not all(
            isinstance(entry, dict)
            and required.issubset(entry)
            and all(isinstance(entry[key], str) for key in required)
            for entry in entries
        ):
            raise RuntimeError(f"Invalid conversation memory format: {self.path}")
        return [{key: entry[key] for key in required} for entry in entries]

    def append(self, *, session: str, user: str, assistant: str) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session": session,
            "user": sanitize_conversation_text(user),
            "assistant": sanitize_conversation_text(assistant),
        }
        entries = self.load()
        entries.append(entry)
        self._save(entries[-self.max_entries :])

    def recent(self, limit: int = 20) -> list[dict[str, str]]:
        if limit <= 0:
            return []
        return self.load()[-limit:]

    def clear(self) -> None:
        self._save([])

    def delete_session(self, session: str) -> int:
        entries = self.load()
        retained = [entry for entry in entries if entry["session"] != session]
        removed = len(entries) - len(retained)
        if removed:
            self._save(retained)
        return removed

    def _save(self, entries: list[dict[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {"version": 1, "entries": entries},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
