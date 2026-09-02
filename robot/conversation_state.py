from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable


class ConversationPhase(StrEnum):
    WAITING = "waiting"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    STOPPED = "stopped"


class ConversationReaction(StrEnum):
    CALM = "calm"
    CURIOUS = "curious"
    WARM = "warm"
    CONFUSED = "confused"
    CAUTIOUS = "cautious"
    HAPPY = "happy"


@dataclass(frozen=True)
class ConversationEvent:
    phase: ConversationPhase
    reaction: ConversationReaction
    reason: str


ConversationEventHandler = Callable[[ConversationEvent], None]


class ConversationStateTracker:
    """Publish domain state transitions without depending on ROS 2."""

    def __init__(self, handler: ConversationEventHandler | None = None) -> None:
        self.handler = handler
        self.current: ConversationEvent | None = None

    def transition(
        self,
        phase: ConversationPhase,
        reaction: ConversationReaction,
        reason: str,
    ) -> ConversationEvent:
        event = ConversationEvent(phase, reaction, reason)
        if event != self.current:
            self.current = event
            if self.handler is not None:
                self.handler(event)
        return event
