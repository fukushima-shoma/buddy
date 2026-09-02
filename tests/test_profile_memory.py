from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from robot.profile_memory import ParentManagedMemory


class ProfileMemoryTest(unittest.TestCase):
    def test_parent_can_set_list_delete_and_clear_facts(self) -> None:
        with TemporaryDirectory() as directory:
            memory = ParentManagedMemory(Path(directory) / "memory.json")
            self.assertEqual(memory.load(), {})
            memory.set("好きな色", "青")
            memory.set("好きな動物", "ぞう")
            self.assertEqual(
                memory.load(),
                {"好きな色": "青", "好きな動物": "ぞう"},
            )
            self.assertTrue(memory.delete("好きな色"))
            self.assertFalse(memory.delete("知らない項目"))
            memory.clear()
            self.assertEqual(memory.load(), {})

    def test_invalid_profile_format_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Invalid"):
                ParentManagedMemory(path).load()
