from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Any
from zoneinfo import ZoneInfo


DEFAULT_CONVERSATION_MEMORY_PATH = Path("data/conversation-memory.sqlite3")
DEFAULT_CONVERSATION_MEMORY_LIMIT = None
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+81[- ]?|0)\d{1,4}[- ]?\d{1,4}[- ]?\d{3,4}(?!\d)"
)
MEMORY_TIMEZONE = ZoneInfo("Asia/Tokyo")
_HISTORY_QUERY_NOISE = (
    "前に",
    "前回",
    "この前",
    "この間",
    "昨日",
    "一昨日",
    "昔",
    "覚えてる",
    "覚えている",
    "覚えて",
    "話した",
    "話してた",
    "話していた",
    "どんなこと",
    "教えて",
    "かな",
    "お話", "おはなし", "の話", "について", "何を", "どんな", "こと",
    "聞かせて", "したよ", "だよ", "だね", "だった", "です",
    "ます", "しよう", "遊ぼう", "今日", "先週", "話したっけ",
)


def sanitize_conversation_text(text: str) -> str:
    normalized = " ".join(text.split())
    normalized = _EMAIL_PATTERN.sub("[メールアドレス削除]", normalized)
    normalized = _PHONE_PATTERN.sub("[電話番号削除]", normalized)
    return normalized[:500]


def _compact_search_text(text: str) -> str:
    return "".join(character for character in text.casefold() if character.isalnum())


def _topic_text(text: str) -> str:
    for phrase in sorted(_HISTORY_QUERY_NOISE, key=len, reverse=True):
        text = text.replace(phrase, " ")
    return text


def _date_filter(query: str, now: datetime) -> tuple[tuple[date, date] | None, str]:
    today = now.astimezone(MEMORY_TIMEZONE).date()
    for phrase, days in (("一昨日", 2), ("おととい", 2), ("昨日", 1), ("きのう", 1), ("今日", 0)):
        if phrase in query:
            day = today - timedelta(days=days)
            return (day, day), query.replace(phrase, "")
    if "先週" in query:
        monday = today - timedelta(days=today.weekday() + 7)
        return (monday, monday + timedelta(days=6)), query.replace("先週", "")
    match = re.search(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日", query)
    if match is None:
        match = re.search(r"(\d{4})-(\d{2})-(\d{2})", query)
    if match:
        try:
            day = date(int(match[1] or today.year), int(match[2]), int(match[3]))
        except ValueError:
            return (date.min, date.min), query[:match.start()] + query[match.end():]
        return (day, day), query[:match.start()] + query[match.end():]
    return None, query


def _search_term_hashes(text: str) -> set[str]:
    compact = _compact_search_text(text)
    if not compact:
        return set()
    chunks = (
        {compact}
        if len(compact) == 1
        else {compact[index : index + 2] for index in range(len(compact) - 1)}
    )
    return {sha256(chunk.encode("utf-8")).hexdigest()[:16] for chunk in chunks}


def _entries_digest(entries: list[dict[str, Any]]) -> str:
    serialized = json.dumps(
        entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return sha256(serialized.encode("utf-8")).hexdigest()


def _build_search_index(entries: list[dict[str, Any]]) -> dict[str, Any]:
    terms: dict[str, list[int]] = {}
    for position, entry in enumerate(entries):
        text = _topic_text(f"{entry['user']} {entry['assistant']}")
        for term in sorted(_search_term_hashes(text)):
            terms.setdefault(term, []).append(position)
    return {
        "algorithm": "topic-bigram-sha256-v2",
        "source_digest": _entries_digest(entries),
        "terms": terms,
        "documents": [
            {
                "entry": position,
                "timestamp": entry["timestamp"],
                "session": entry["session"],
                "summary": entry["user"][:120] + " / " + entry["assistant"][:120],
            }
            for position, entry in enumerate(entries)
        ],
    }


class JsonConversationMemoryStore:
    def __init__(
        self,
        path: Path = DEFAULT_CONVERSATION_MEMORY_PATH,
        *,
        max_entries: int | None = DEFAULT_CONVERSATION_MEMORY_LIMIT,
    ) -> None:
        self.path = path.expanduser()
        self.max_entries = None if max_entries is None else max(1, max_entries)
        self._index: dict[str, Any] | None = None

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            self._index = None
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
        result = []
        for entry in entries:
            value = {key: entry[key] for key in required}
            if "turn" in entry:
                if type(entry["turn"]) is not int or entry["turn"] < 1:
                    raise RuntimeError(f"Invalid conversation turn metadata: {self.path}")
                value["turn"] = entry["turn"]
            result.append(value)
        index = payload.get("index")
        terms = index.get("terms") if isinstance(index, dict) else None
        valid_index = (
            isinstance(index, dict)
            and index.get("algorithm") == "topic-bigram-sha256-v2"
            and index.get("source_digest") == _entries_digest(result)
            and isinstance(terms, dict)
            and all(
                isinstance(term, str) and isinstance(positions, list)
                and all(type(p) is int and 0 <= p < len(result) for p in positions)
                for term, positions in terms.items()
            )
        )
        self._index = index if valid_index else None
        return result

    def append(self, *, session: str, user: str, assistant: str, turn: int | None = None) -> None:
        if turn is not None and (type(turn) is not int or turn < 1):
            raise ValueError("Conversation turn must be a positive integer.")
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session": session,
            "user": sanitize_conversation_text(user),
            "assistant": sanitize_conversation_text(assistant),
        }
        if turn is not None:
            entry["turn"] = turn
        entries = self.load()
        entries.append(entry)
        self._save(entries if self.max_entries is None else entries[-self.max_entries :])

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return self.load()[-limit:]

    def relevant(
        self,
        query: str,
        *,
        limit: int = 4,
        exclude_session: str | None = None,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Find a few relevant past exchanges using the persisted local index."""
        if limit <= 0:
            return []
        entries = self.load()
        window, query = _date_filter(query, now or datetime.now(MEMORY_TIMEZONE))
        available = []
        for position, entry in enumerate(entries):
            if entry["session"] == exclude_session:
                continue
            if window:
                try:
                    timestamp = datetime.fromisoformat(entry["timestamp"])
                    if timestamp.tzinfo is None:
                        continue
                    day = timestamp.astimezone(MEMORY_TIMEZONE).date()
                except ValueError:
                    continue
                if not window[0] <= day <= window[1]:
                    continue
            available.append((position, entry))
        if not available:
            return []

        indexed_query = _topic_text(query)
        query_terms = _search_term_hashes(indexed_query)
        if self._index is None:
            # Version-1 logs and invalid derived indexes are rebuilt locally.
            self._save(entries)
        index = self._index
        assert index is not None
        scores: dict[int, int] = {}
        for term in query_terms:
            for position in index["terms"].get(term, []):
                scores[position] = scores.get(position, 0) + 1

        compact_query = _compact_search_text(indexed_query).strip("のはをにがとでねよ")
        date_only = window is not None and len(compact_query) < 2
        minimum_score = 1 if len(compact_query) == 2 else 2
        ranked = sorted(
            (
                (scores.get(position, 0), position, entry)
                for position, entry in available
                if date_only or scores.get(position, 0) >= minimum_score
            ),
            key=lambda item: (item[0], item[1]),
            reverse=True,
        )
        if ranked:
            return [entry for _, _, entry in ranked[:limit]]
        return []

    def clear(self) -> None:
        self._save([])

    def delete_session(self, session: str) -> int:
        entries = self.load()
        retained = [entry for entry in entries if entry["session"] != session]
        removed = len(entries) - len(retained)
        if removed:
            self._save(retained)
        return removed

    def _save(self, entries: list[dict[str, Any]]) -> None:
        index = _build_search_index(entries)
        temporary: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # mkstemp creates the file with mode 0600 before any text is written.
            fd, name = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
            temporary = Path(name)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(
                    {"version": 2, "entries": entries, "index": index},
                    stream, ensure_ascii=False, indent=2,
                )
                stream.write("\n")
            temporary.replace(self.path)
            self._index = index
        except OSError as exc:
            raise RuntimeError(f"Could not save conversation memory: {self.path}") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


class ConversationMemoryStore:
    """SQLite storage with one-time, verified import of a sibling JSON file."""

    def __init__(self, path: Path = DEFAULT_CONVERSATION_MEMORY_PATH, *,
                 max_entries: int | None = None) -> None:
        requested = path.expanduser()
        # Old --file ...json invocations keep working against the sibling DB.
        self.path = requested.with_suffix(".sqlite3") if requested.suffix == ".json" else requested
        self.legacy_path = self.path.with_suffix(".json")
        self.max_entries = None if max_entries is None else max(1, max_entries)

    @contextmanager
    def _connect(self):
        connection = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(fd)
            self.path.chmod(0o600)
            connection = sqlite3.connect(self.path, timeout=1.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA secure_delete=ON")
            # A marker makes migration exactly-once, including after clear().
            if connection.execute("PRAGMA user_version").fetchone()[0] == 0:
                self._initialize(connection)
            elif connection.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise RuntimeError("Unsupported conversation database version.")
            yield connection
            connection.commit()
        except (OSError, sqlite3.Error) as exc:
            if connection is not None:
                connection.rollback()
            raise RuntimeError(f"Conversation database unavailable: {self.path}") from exc
        finally:
            if connection is not None:
                connection.close()

    def _initialize(self, db: sqlite3.Connection) -> None:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("PRAGMA user_version").fetchone()[0] != 0:
            db.commit()
            return
        db.execute("""CREATE TABLE exchanges (
            id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, day TEXT,
            session TEXT NOT NULL, user TEXT NOT NULL, assistant TEXT NOT NULL,
            turn INTEGER, summary TEXT NOT NULL)""")
        db.execute("""CREATE TABLE terms (
            term TEXT NOT NULL, exchange_id INTEGER NOT NULL
            REFERENCES exchanges(id) ON DELETE CASCADE,
            PRIMARY KEY (term, exchange_id)) WITHOUT ROWID""")
        db.execute("CREATE INDEX terms_exchange ON terms(exchange_id)")
        db.execute("CREATE INDEX exchanges_day ON exchanges(day, id)")
        db.execute("CREATE INDEX exchanges_session ON exchanges(session)")
        if self.legacy_path.exists():
            entries = JsonConversationMemoryStore(self.legacy_path).load()
            for entry in entries:
                self._insert(db, entry)
            copied = [self._entry(row) for row in db.execute("SELECT * FROM exchanges ORDER BY id")]
            if len(copied) != len(entries) or _entries_digest(copied) != _entries_digest(entries):
                raise RuntimeError("Conversation migration verification failed.")
            # The original JSON is a recoverable migration backup.
            self.legacy_path.chmod(0o600)
        db.execute("PRAGMA user_version=1")
        db.commit()

    @staticmethod
    def _entry(row: sqlite3.Row) -> dict[str, Any]:
        entry = {key: row[key] for key in ("timestamp", "session", "user", "assistant")}
        if row["turn"] is not None:
            entry["turn"] = row["turn"]
        return entry

    @staticmethod
    def _insert(db: sqlite3.Connection, entry: dict[str, Any]) -> None:
        try:
            timestamp = datetime.fromisoformat(entry["timestamp"])
            day = timestamp.astimezone(MEMORY_TIMEZONE).date().isoformat() if timestamp.tzinfo else None
        except ValueError:
            day = None
        cursor = db.execute(
            "INSERT INTO exchanges(timestamp,day,session,user,assistant,turn,summary) VALUES(?,?,?,?,?,?,?)",
            (entry["timestamp"], day, entry["session"], entry["user"], entry["assistant"],
             entry.get("turn"), entry["user"][:120] + " / " + entry["assistant"][:120]),
        )
        terms = _search_term_hashes(_topic_text(entry["user"] + " " + entry["assistant"]))
        db.executemany("INSERT INTO terms(term,exchange_id) VALUES(?,?)",
                       ((term, cursor.lastrowid) for term in terms))

    def append(self, *, session: str, user: str, assistant: str, turn: int | None = None) -> None:
        if turn is not None and (type(turn) is not int or turn < 1):
            raise ValueError("Conversation turn must be a positive integer.")
        entry = dict(timestamp=datetime.now(timezone.utc).isoformat(), session=session,
                     user=sanitize_conversation_text(user), assistant=sanitize_conversation_text(assistant))
        if turn is not None:
            entry["turn"] = turn
        with self._connect() as db:
            self._insert(db, entry)
            if self.max_entries is not None:
                db.execute("DELETE FROM exchanges WHERE id NOT IN "
                           "(SELECT id FROM exchanges ORDER BY id DESC LIMIT ?)", (self.max_entries,))

    def load(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            return [self._entry(row) for row in db.execute("SELECT * FROM exchanges ORDER BY id")]

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        with self._connect() as db:
            rows = db.execute("SELECT * FROM exchanges ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [self._entry(row) for row in reversed(rows)]

    def relevant(self, query: str, *, limit: int = 4, exclude_session: str | None = None,
                 now: datetime | None = None) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        window, query = _date_filter(query, now or datetime.now(MEMORY_TIMEZONE))
        topic = _topic_text(query)
        compact = _compact_search_text(topic).strip("のはをにがとでねよ")
        date_only = window is not None and len(compact) < 2
        terms = sorted(_search_term_hashes(topic))
        if not date_only and not terms:
            return []
        filters, params = [], []
        if exclude_session is not None:
            filters.append("e.session != ?")
            params.append(exclude_session)
        if window:
            filters.append("e.day BETWEEN ? AND ?")
            params.extend(day.isoformat() for day in window)
        where = " AND ".join(filters) or "1"
        with self._connect() as db:
            if date_only:
                rows = db.execute(f"SELECT e.* FROM exchanges e WHERE {where} ORDER BY e.id DESC LIMIT ?",
                                  (*params, limit))
            else:
                placeholders = ",".join("?" for _ in terms)
                rows = db.execute(
                    f"""SELECT e.*, COUNT(*) AS score FROM terms t
                    JOIN exchanges e ON e.id=t.exchange_id
                    WHERE t.term IN ({placeholders}) AND {where}
                    GROUP BY e.id HAVING COUNT(*) >= ?
                    ORDER BY score DESC, e.id DESC LIMIT ?""",
                    (*terms, *params, 1 if len(compact) == 2 else 2, limit),
                )
            return [self._entry(row) for row in rows]

    def clear(self) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM exchanges")
        # Explicit deletion also clears the migration backup.
        if self.legacy_path.exists():
            JsonConversationMemoryStore(self.legacy_path).clear()

    def delete_session(self, session: str) -> int:
        with self._connect() as db:
            removed = db.execute("DELETE FROM exchanges WHERE session=?", (session,)).rowcount
        if self.legacy_path.exists():
            JsonConversationMemoryStore(self.legacy_path).delete_session(session)
        return removed

    def _save(self, entries: list[dict[str, Any]]) -> None:
        """Bulk replacement used for offline fixtures; live writes use append."""
        with self._connect() as db:
            db.execute("DELETE FROM exchanges")
            for entry in entries:
                self._insert(db, entry)
