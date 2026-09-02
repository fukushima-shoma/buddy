from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from robot.profile_memory import ParentManagedMemory
from robot.spoken_profile_memory import SpokenProfileMemory


class SpokenProfileMemoryTest(unittest.TestCase):
    def test_allowed_preferences_are_saved_recalled_and_deleted_locally(self) -> None:
        with TemporaryDirectory() as directory:
            store = ParentManagedMemory(Path(directory) / "profile.json")
            memory = SpokenProfileMemory(store)

            self.assertEqual(
                memory.handle("ぼくの好きな色は青だよ"),
                "好きな色は、青って覚えたよ。",
            )
            self.assertEqual(store.load(), {"好きな色": "青"})
            self.assertEqual(memory.handle("好きな色は何？"), "好きな色は、青だよ。")
            self.assertEqual(memory.handle("好きな色を忘れて"), "好きな色は忘れたよ。")
            self.assertEqual(store.load(), {})

    def test_personal_and_unlisted_facts_are_not_saved(self) -> None:
        with TemporaryDirectory() as directory:
            store = ParentManagedMemory(Path(directory) / "profile.json")
            memory = SpokenProfileMemory(store)

            self.assertIsNone(memory.handle("ぼくの名前は太郎だよ"))
            self.assertIsNone(memory.handle("住所は東京都だよ"))
            self.assertEqual(store.load(), {})

    def test_overlong_preference_is_not_saved(self) -> None:
        with TemporaryDirectory() as directory:
            store = ParentManagedMemory(Path(directory) / "profile.json")
            memory = SpokenProfileMemory(store)

            self.assertIsNone(memory.handle(f"好きな色は{'青' * 21}"))
            self.assertEqual(store.load(), {})
