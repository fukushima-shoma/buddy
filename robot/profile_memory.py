from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping


DEFAULT_PROFILE_MEMORY_PATH = Path("data/buddy-memory.json")
MAX_PROFILE_FACTS = 20


def _clean(value: str, *, label: str, limit: int) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError(f"{label} must not be empty")
    if len(cleaned) > limit:
        raise ValueError(f"{label} must be {limit} characters or fewer")
    return cleaned


class ParentManagedMemory:
    """Small local profile edited explicitly by a supervising adult."""

    def __init__(self, path: Path = DEFAULT_PROFILE_MEMORY_PATH) -> None:
        self.path = path.expanduser()

    def load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Could not read profile memory: {self.path}") from exc
        facts = payload.get("facts") if isinstance(payload, dict) else None
        if not isinstance(facts, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in facts.items()
        ):
            raise RuntimeError(f"Invalid profile memory format: {self.path}")
        return dict(facts)

    def set(self, key: str, value: str) -> None:
        key = _clean(key, label="key", limit=40)
        value = _clean(value, label="value", limit=120)
        facts = self.load()
        if key not in facts and len(facts) >= MAX_PROFILE_FACTS:
            raise ValueError(f"profile memory is limited to {MAX_PROFILE_FACTS} facts")
        facts[key] = value
        self._save(facts)

    def delete(self, key: str) -> bool:
        key = _clean(key, label="key", limit=40)
        facts = self.load()
        removed = facts.pop(key, None) is not None
        if removed:
            self._save(facts)
        return removed

    def clear(self) -> None:
        self._save({})

    def _save(self, facts: Mapping[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps({"version": 1, "facts": facts}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)


def format_profile_memory(facts: Mapping[str, str]) -> str:
    if not facts:
        return ""
    lines = [
        "以下は保護者が明示的に登録した情報です。会話に関係する場合だけ自然に使い、",
        "登録されていない情報を推測したり、追加の個人情報を尋ねたりしないでください。",
    ]
    lines.extend(f"- {key}: {value}" for key, value in sorted(facts.items()))
    return "\n".join(lines)
