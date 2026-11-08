from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest

from robot.shared_experience_memory import (
    SharedExperienceStore,
    SpokenSharedExperienceMemory,
    clean_experience_summary,
)


class SharedExperienceMemoryTest(unittest.TestCase):
    def test_memory_survives_store_recreation_and_deduplicates(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "experiences.json"
            first_store = SharedExperienceStore(path)
            first = first_store.remember("赤い車をロケット号と名付けた")
            duplicate = first_store.remember("赤い車をロケット号と名付けた")

            second_store = SharedExperienceStore(path)

            self.assertEqual(first["id"], duplicate["id"])
            self.assertEqual(second_store.load(), [first])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_relevant_prioritizes_matching_memory_and_keeps_old_entries(self) -> None:
        with TemporaryDirectory() as directory:
            store = SharedExperienceStore(Path(directory) / "experiences.json")
            matching = store.remember("青い車をロケット号と名付けた")
            store.remember("雨の日にカエルの歌を作った")

            relevant = store.relevant("ロケット号は速いかな", limit=1)

            self.assertEqual(relevant, [matching])
            self.assertEqual(store.relevant("きょうのおやつ"), [])
            self.assertEqual(len(store.load()), 2)

    def test_memory_can_be_deleted_but_is_not_expired_automatically(self) -> None:
        with TemporaryDirectory() as directory:
            store = SharedExperienceStore(Path(directory) / "experiences.json")
            entry = store.remember("段ボールの車を作った")

            self.assertTrue(store.delete(entry["id"]))
            self.assertFalse(store.delete(entry["id"]))
            self.assertEqual(store.load(), [])

    def test_personal_contact_and_school_details_are_rejected(self) -> None:
        for summary in (
            "連絡先はchild@example.com",
            "電話番号は090-1234-5678",
            "さくら小学校に通っている",
            "住所は東京都一丁目",
            "誕生日は4月3日",
        ):
            with self.subTest(summary=summary):
                with self.assertRaisesRegex(ValueError, "personal information"):
                    clean_experience_summary(summary)

    def test_spoken_requests_remember_recall_and_forget_without_api(self) -> None:
        with TemporaryDirectory() as directory:
            store = SharedExperienceStore(Path(directory) / "experiences.json")
            memory = SpokenSharedExperienceMemory(store)

            remembered = memory.handle("赤い車をロケット号と名付けたことを覚えて")
            recalled = memory.handle("何を覚えてる？")
            forgotten = memory.handle("赤い車をロケット号と名付けたことを忘れて")

            self.assertIn("いっしょの思い出として覚えた", remembered or "")
            self.assertIn("ロケット号", recalled or "")
            self.assertIn("思い出は忘れた", forgotten or "")
            self.assertEqual(store.load(), [])

    def test_unrelated_speech_is_not_handled(self) -> None:
        with TemporaryDirectory() as directory:
            memory = SpokenSharedExperienceMemory(
                SharedExperienceStore(Path(directory) / "experiences.json")
            )

            self.assertIsNone(memory.handle("赤い車で遊ぼう"))


if __name__ == "__main__":
    unittest.main()
