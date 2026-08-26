from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from robot.conversation_memory import (
    ConversationMemoryStore,
    format_conversation_memory,
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

    def test_history_can_be_formatted_and_cleared(self) -> None:
        with TemporaryDirectory() as directory:
            store = ConversationMemoryStore(Path(directory) / "history.json")
            store.append(session="a", user="青が好き", assistant="青、きれいだね")

            context = format_conversation_memory(store.load())
            self.assertIn("子ども: 青が好き", context)
            self.assertIn("個人情報", context)
            store.clear()
            self.assertEqual(store.load(), [])

    def test_email_and_phone_number_are_redacted_before_storage(self) -> None:
        text = "連絡は child@example.com か 090-1234-5678 だよ"

        sanitized = sanitize_conversation_text(text)

        self.assertNotIn("child@example.com", sanitized)
        self.assertNotIn("090-1234-5678", sanitized)
        self.assertIn("[メールアドレス削除]", sanitized)
        self.assertIn("[電話番号削除]", sanitized)
