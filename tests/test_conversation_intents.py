import unittest

from robot.conversation_intents import (
    is_farewell_transcript,
    is_mobility_start_transcript,
    is_mobility_stop_transcript,
    is_power_status_transcript,
    normalize_exact_phrase,
)


class ConversationIntentsTest(unittest.TestCase):
    def test_normalization_removes_width_spacing_and_punctuation(self) -> None:
        self.assertEqual(normalize_exact_phrase(" ストップ！ "), "ストップ")

    def test_commands_must_match_the_complete_phrase(self) -> None:
        self.assertTrue(is_farewell_transcript("またね。"))
        self.assertTrue(is_mobility_start_transcript("ついて来て！"))
        self.assertTrue(is_mobility_stop_transcript("止まって。"))
        self.assertTrue(is_power_status_transcript("バッテリーは大丈夫？"))
        self.assertFalse(is_mobility_stop_transcript("止まっているね"))
        self.assertFalse(is_power_status_transcript("電池大丈夫って聞いた"))


if __name__ == "__main__":
    unittest.main()
