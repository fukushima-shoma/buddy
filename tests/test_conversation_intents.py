import unittest

from robot.conversation_intents import (
    DEFAULT_FAREWELL_REPLY,
    DEFAULT_INACTIVITY_REPLY,
    LOCAL_SHORT_REPLIES,
    LocalShortReplyController,
    MOBILITY_FAREWELL_REPLY,
    is_ambiguous_mobility_transcript,
    is_farewell_transcript,
    is_mobility_cancel_transcript,
    is_mobility_confirm_transcript,
    is_mobility_start_transcript,
    is_mobility_stop_transcript,
    is_power_status_transcript,
    is_repeat_reply_transcript,
    normalize_exact_phrase,
)


class ConversationIntentsTest(unittest.TestCase):
    def test_session_end_replies_keep_buddys_discovery_identity(self) -> None:
        self.assertIn("タイヤ", DEFAULT_FAREWELL_REPLY)
        self.assertIn("タイヤ", DEFAULT_INACTIVITY_REPLY)
        self.assertTrue(MOBILITY_FAREWELL_REPLY.startswith("止まったよ。"))
        self.assertIn("タイヤ", MOBILITY_FAREWELL_REPLY)

    def test_normalization_removes_width_spacing_and_punctuation(self) -> None:
        self.assertEqual(normalize_exact_phrase(" ストップ！ "), "ストップ")

    def test_commands_must_match_the_complete_phrase(self) -> None:
        self.assertTrue(is_farewell_transcript("またね。"))
        self.assertTrue(is_mobility_start_transcript("ついて来て！"))
        self.assertTrue(is_mobility_stop_transcript("止まって。"))
        self.assertTrue(is_power_status_transcript("バッテリーは大丈夫？"))
        self.assertFalse(is_mobility_stop_transcript("止まっているね"))
        self.assertFalse(is_power_status_transcript("電池大丈夫って聞いた"))

    def test_mobility_confirmation_and_ambiguous_commands_are_exact(self) -> None:
        self.assertTrue(is_mobility_confirm_transcript("はい！"))
        self.assertTrue(is_mobility_cancel_transcript("やめる"))
        self.assertTrue(is_ambiguous_mobility_transcript("進んで。"))
        self.assertFalse(is_mobility_confirm_transcript("はいって言った"))
        self.assertFalse(is_ambiguous_mobility_transcript("前に進んでいるね"))

    def test_repeat_request_requires_an_exact_phrase(self) -> None:
        self.assertTrue(is_repeat_reply_transcript("もう一回言って！"))
        self.assertTrue(is_repeat_reply_transcript("なんて言った？"))
        self.assertFalse(is_repeat_reply_transcript("もう一回言ってと頼んだ"))

    def test_local_short_replies_match_only_safe_complete_phrases(self) -> None:
        controller = LocalShortReplyController()

        reply = controller.reply("ありがとう！")

        self.assertIsNotNone(reply)
        assert reply is not None
        self.assertEqual(reply.intent, "thanks")
        self.assertIsNone(controller.reply("ありがとうって言った"))
        self.assertIsNone(controller.reply("うん"))

    def test_local_short_replies_rotate_within_each_intent(self) -> None:
        controller = LocalShortReplyController()

        replies = [controller.reply("できた") for _ in range(4)]
        texts = [reply.text for reply in replies if reply is not None]

        self.assertEqual(texts[:3], list(LOCAL_SHORT_REPLIES["success"]))
        self.assertEqual(texts[3], texts[0])

    def test_every_local_short_reply_fits_the_child_length_target(self) -> None:
        for replies in LOCAL_SHORT_REPLIES.values():
            for reply in replies:
                with self.subTest(reply=reply):
                    self.assertLessEqual(len(reply), 25)


if __name__ == "__main__":
    unittest.main()
