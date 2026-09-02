import unittest

from robot.conversation_state import (
    ConversationEvent,
    ConversationPhase,
    ConversationReaction,
    ConversationStateTracker,
)


class ConversationStateTest(unittest.TestCase):
    def test_tracker_emits_typed_transitions_and_suppresses_duplicates(self) -> None:
        events: list[ConversationEvent] = []
        tracker = ConversationStateTracker(events.append)

        first = tracker.transition(
            ConversationPhase.LISTENING,
            ConversationReaction.CALM,
            "awaiting-speech",
        )
        tracker.transition(
            ConversationPhase.LISTENING,
            ConversationReaction.CALM,
            "awaiting-speech",
        )
        final = tracker.transition(
            ConversationPhase.THINKING,
            ConversationReaction.CURIOUS,
            "transcript-ready",
        )

        self.assertEqual(events, [first, final])
        self.assertEqual(tracker.current, final)
