from types import SimpleNamespace
import unittest

from robot.conversation import (
    BUDDY_INSTRUCTIONS,
    CHILD_REPLY_INSTRUCTIONS,
    DEFAULT_REPLY_MODEL,
    MockReplyGenerator,
    OpenAIReplyGenerator,
    get_reply_instructions,
)
from robot.reply_cli import build_parser, create_reply_generator


class FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            id=f"resp_{len(self.calls)}",
            output_text="  こんにちは！  ",
        )


class ConversationTest(unittest.TestCase):
    def test_mock_reply_generator_is_deterministic(self) -> None:
        generator = MockReplyGenerator("モック返答")

        result = generator.reply("こんにちは")

        self.assertEqual(result, "モック返答")
        self.assertEqual(generator.inputs, ["こんにちは"])

    def test_openai_reply_uses_responses_api_with_app_instructions(self) -> None:
        responses = FakeResponses()
        client = SimpleNamespace(responses=responses)
        generator = OpenAIReplyGenerator(client=client)

        result = generator.reply("こんにちは")

        self.assertEqual(result, "こんにちは！")
        self.assertEqual(responses.calls[0]["model"], DEFAULT_REPLY_MODEL)
        self.assertEqual(responses.calls[0]["reasoning"], {"effort": "low"})
        self.assertEqual(responses.calls[0]["instructions"], BUDDY_INSTRUCTIONS)
        self.assertEqual(responses.calls[0]["input"], "こんにちは")

    def test_openai_reply_rejects_empty_text_without_calling_api(self) -> None:
        responses = FakeResponses()
        client = SimpleNamespace(responses=responses)
        generator = OpenAIReplyGenerator(client=client)

        with self.assertRaisesRegex(ValueError, "empty text"):
            generator.reply("   ")

        self.assertEqual(responses.calls, [])

    def test_prompt_contains_child_safety_boundaries(self) -> None:
        self.assertIn("AI", BUDDY_INSTRUCTIONS)
        self.assertIn("個人情報", BUDDY_INSTRUCTIONS)
        self.assertIn("信頼できる大人", BUDDY_INSTRUCTIONS)

    def test_child_prompt_uses_short_simple_safe_conversation_rules(self) -> None:
        instructions = get_reply_instructions(True)

        self.assertEqual(instructions, CHILD_REPLY_INSTRUCTIONS)
        self.assertIn("質問は1つ", instructions)
        self.assertIn("二択", instructions)
        self.assertIn("言った？", instructions)
        self.assertIn("個人情報", instructions)
        self.assertIn("秘密", instructions)
        self.assertIn("信頼できる大人", instructions)

    def test_parent_managed_profile_is_added_to_instructions(self) -> None:
        instructions = get_reply_instructions(True, {"好きな色": "青"})

        self.assertIn("好きな色: 青", instructions)
        self.assertIn("保護者", instructions)

    def test_session_context_passes_previous_response_id(self) -> None:
        responses = FakeResponses()
        client = SimpleNamespace(responses=responses)
        generator = OpenAIReplyGenerator(
            client=client,
            remember_context=True,
        )

        generator.reply("ぼくの好きな色は青だよ")
        generator.reply("何色が好きだと言った？")

        self.assertNotIn("previous_response_id", responses.calls[0])
        self.assertEqual(responses.calls[1]["previous_response_id"], "resp_1")
        self.assertEqual(responses.calls[1]["instructions"], BUDDY_INSTRUCTIONS)

    def test_session_context_resets_after_configured_turns(self) -> None:
        responses = FakeResponses()
        client = SimpleNamespace(responses=responses)
        generator = OpenAIReplyGenerator(
            client=client,
            remember_context=True,
            max_context_turns=2,
        )

        generator.reply("1")
        generator.reply("2")
        generator.reply("3")

        self.assertEqual(responses.calls[1]["previous_response_id"], "resp_1")
        self.assertNotIn("previous_response_id", responses.calls[2])

    def test_cli_defaults_do_not_call_openai(self) -> None:
        args = build_parser().parse_args(["こんにちは"])

        self.assertEqual(args.backend, "mock")
        self.assertEqual(args.model, DEFAULT_REPLY_MODEL)
        self.assertFalse(args.child_mode)

    def test_cli_can_enable_child_mode(self) -> None:
        args = build_parser().parse_args(["こんにちは", "--child-mode"])

        self.assertTrue(args.child_mode)

    def test_factory_defaults_to_mock(self) -> None:
        generator = create_reply_generator(
            "mock", model=DEFAULT_REPLY_MODEL, mock_reply="安全"
        )

        self.assertIsInstance(generator, MockReplyGenerator)


if __name__ == "__main__":
    unittest.main()
