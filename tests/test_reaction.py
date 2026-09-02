import json
import unittest

from robot.conversation_state import (
    ConversationEvent,
    ConversationPhase,
    ConversationReaction,
)
from robot.reaction import conversation_event_from_json, reaction_command_for


class ReactionTest(unittest.TestCase):
    def test_happy_event_maps_to_semantic_driver_command(self) -> None:
        command = reaction_command_for(
            ConversationEvent(
                ConversationPhase.SPEAKING,
                ConversationReaction.HAPPY,
                "child-game",
            )
        )

        self.assertEqual(command.expression, "big-smile")
        self.assertEqual(command.light_animation, "sparkle")
        self.assertEqual(command.sound_cue, "success")
        self.assertEqual(json.loads(command.to_json())["light_color"], "green")

    def test_lifecycle_phases_override_reaction(self) -> None:
        stopped = reaction_command_for(
            ConversationEvent(
                ConversationPhase.STOPPED,
                ConversationReaction.CALM,
                "conversation-ended",
            )
        )
        waiting = reaction_command_for(
            ConversationEvent(
                ConversationPhase.WAITING,
                ConversationReaction.CALM,
                "waiting-for-trigger",
            )
        )

        self.assertEqual(stopped.light_color, "off")
        self.assertEqual(waiting.expression, "attentive")

    def test_event_json_is_validated_at_transport_boundary(self) -> None:
        event = conversation_event_from_json(
            '{"phase":"thinking","reaction":"curious","reason":"reply"}'
        )

        self.assertEqual(event.phase, ConversationPhase.THINKING)
        self.assertEqual(event.reaction, ConversationReaction.CURIOUS)
        with self.assertRaises(ValueError):
            conversation_event_from_json('{"phase":"unknown"}')


if __name__ == "__main__":
    unittest.main()
