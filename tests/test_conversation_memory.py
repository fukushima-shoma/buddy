from pathlib import Path
from datetime import datetime
import json
import stat
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from robot.conversation_memory import (
    ConversationMemoryStore,
    JsonConversationMemoryStore,
    sanitize_conversation_text,
)


class ConversationMemoryTest(unittest.TestCase):
    def test_append_retains_only_configured_number_of_turns(self) -> None:
        with TemporaryDirectory() as directory:
            store = ConversationMemoryStore(
                Path(directory) / "history.json",
                max_entries=2,
            )
            store.append(session="a", user="1", assistant="一")
            store.append(session="a", user="2", assistant="二")
            store.append(session="b", user="3", assistant="三")

            entries = store.load()
            self.assertEqual([entry["user"] for entry in entries], ["2", "3"])
            self.assertEqual(len(store.recent(1)), 1)
            self.assertEqual(store.delete_session("a"), 1)
            self.assertEqual([entry["user"] for entry in store.load()], ["3"])

    def test_history_can_be_cleared(self) -> None:
        with TemporaryDirectory() as directory:
            store = ConversationMemoryStore(Path(directory) / "history.json")
            store.append(session="a", user="青が好き", assistant="青、きれいだね")

            store.clear()
            self.assertEqual(store.load(), [])

    def test_email_and_phone_number_are_redacted_before_storage(self) -> None:
        text = "連絡は child@example.com か 090-1234-5678 だよ"

        sanitized = sanitize_conversation_text(text)

        self.assertNotIn("child@example.com", sanitized)
        self.assertNotIn("090-1234-5678", sanitized)
        self.assertIn("[メールアドレス削除]", sanitized)
        self.assertIn("[電話番号削除]", sanitized)

    def test_optional_turn_metadata_preserves_old_entries(self) -> None:
        with TemporaryDirectory() as directory:
            store = ConversationMemoryStore(Path(directory) / "history.json")
            store.append(session="old", user="赤", assistant="赤だね")
            store.append(session="new", turn=7, user="青", assistant="青だね")
            self.assertNotIn("turn", store.load()[0])
            self.assertEqual(store.load()[1]["turn"], 7)
            with self.assertRaises(ValueError):
                store.append(session="new", turn=0, user="青", assistant="青だね")

    def test_search_index_is_persisted_and_file_is_private(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            store = ConversationMemoryStore(path)
            store.append(session="old", user="1", assistant="一")
            store.append(session="latest", user="2", assistant="二")
            store.append(session="latest", user="3", assistant="三")

            with sqlite3.connect(store.path) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM exchanges").fetchone()[0], 3)
                self.assertGreater(db.execute("SELECT count(*) FROM terms").fetchone()[0], 0)
            self.assertEqual(stat.S_IMODE(store.path.stat().st_mode), 0o600)

    def test_search_crosses_sessions_without_explicit_recall_phrase(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            store = ConversationMemoryStore(path)
            store.append(session="old", user="赤い車をロケット号と名付けた", assistant="出発！")
            for index in range(105):
                store.append(session="later", user=f"積み木{index}", assistant="できたね")
            store.append(session="current", user="ロケット号", assistant="走ろう")
            reopened = ConversationMemoryStore(path)
            found = reopened.relevant("ロケット号で遊ぼう", exclude_session="current")
            self.assertEqual([entry["session"] for entry in found], ["old"])
            self.assertEqual(len(reopened.load()), 107)
            self.assertEqual(reopened.relevant("昨日のペンギン覚えてる？"), [])
            self.assertEqual(reopened.relevant("こんにちは"), [])
            self.assertEqual(reopened.relevant("前回何を話した"), [])
            self.assertLessEqual(len(reopened.relevant("積み木")), 4)
            reopened.delete_session("old")
            self.assertEqual(reopened.relevant("ロケット号", exclude_session="current"), [])
            reopened.clear()
            with sqlite3.connect(store.path) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM terms").fetchone()[0], 0)

    def test_date_search_uses_japan_day_boundaries_and_never_falls_back(self):
        with TemporaryDirectory() as directory:
            store = ConversationMemoryStore(Path(directory) / "history.json")
            store._save([
                {"timestamp": stamp, "session": stamp, "user": "ロケット号で遊んだ",
                 "assistant": "出発"}
                for stamp in [
                    "2026-09-13T23:00:00+09:00",  # outside last week
                    "2026-09-14T00:00:00+09:00",
                    "2026-09-20T23:59:00+09:00",
                    "2026-09-21T14:59:00+00:00",  # yesterday in Japan
                    "2026-09-21T15:00:00+00:00",  # today in Japan
                ]
            ])
            now = datetime.fromisoformat("2026-09-22T10:00:00+09:00")
            self.assertEqual(len(store.relevant("先週のロケット号", now=now)), 2)
            self.assertEqual(len(store.relevant("昨日何を話した", now=now)), 1)
            self.assertEqual(len(store.relevant("一昨日のロケット号", now=now)), 1)
            self.assertEqual(len(store.relevant("9月14日の話", now=now)), 1)
            self.assertEqual(len(store.relevant("2026-09-14の話", now=now)), 1)
            self.assertEqual(store.relevant("9月30日のロケット号", now=now), [])
            self.assertEqual(store.relevant("2月30日の話", now=now), [])

    def test_legacy_migration_is_verified_and_runs_only_once(self):
        from unittest.mock import patch
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            entry = {"timestamp": "2026-09-01T00:00:00+00:00", "session": "old",
                     "user": "ロケット号", "assistant": "出発"}
            path.write_text(json.dumps({"version": 1, "entries": [entry]}))
            store = ConversationMemoryStore(path)
            self.assertEqual(len(store.relevant("ロケット号")), 1)
            with patch("robot.conversation_memory._build_search_index",
                       side_effect=AssertionError("must use persisted index")):
                self.assertEqual(len(ConversationMemoryStore(path).relevant("ロケット号")), 1)
            self.assertEqual(store.load(), [entry])
            self.assertEqual(json.loads(path.read_text())["entries"], [entry])
            store.append(session="new", user="ペンギン", assistant="泳いだ")
            self.assertEqual(len(ConversationMemoryStore(path).load()), 2)
            store.delete_session("old")
            self.assertEqual(json.loads(path.read_text())["entries"], [])
            store.clear()
            self.assertEqual(ConversationMemoryStore(path).load(), [])

    def test_migration_failure_rolls_back_and_source_is_untouched(self):
        from unittest.mock import patch
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            legacy = JsonConversationMemoryStore(path)
            legacy.append(session="old", user="ロケット号", assistant="出発")
            before = path.read_bytes()
            store = ConversationMemoryStore(path)
            with patch.object(store, "_insert", side_effect=RuntimeError("injected")):
                with self.assertRaises(RuntimeError):
                    store.load()
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(store.load(), legacy.load())

    def test_sqlite_search_matches_legacy_and_append_only_indexes_new_exchange(self):
        from unittest.mock import patch
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            legacy = JsonConversationMemoryStore(path)
            for session, user in (("old", "ロケット号で月まで行こう"), ("new", "積み木の城")):
                legacy.append(session=session, user=user, assistant="楽しみだね")
            store = ConversationMemoryStore(path)
            for query in ("ロケット号", "積み木", "ペンギン"):
                self.assertEqual(store.relevant(query), legacy.relevant(query))
            with patch.object(store, "_insert", wraps=store._insert) as insert:
                store.append(session="current", user="ロケット号", assistant="出発")
                self.assertEqual(insert.call_count, 1)
            with patch.object(store, "load", side_effect=AssertionError("no full scan")):
                self.assertEqual(len(store.relevant("ロケット号")), 2)
