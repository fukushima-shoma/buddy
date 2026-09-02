from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from robot.conversation_state import (
    ConversationEvent,
    ConversationPhase,
    ConversationReaction,
)


@dataclass(frozen=True)
class ReactionCommand:
    """Semantic output for replaceable face, light, and sound drivers."""

    expression: str
    light_color: str
    light_animation: str
    sound_cue: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> "ReactionCommand":
        try:
            values = json.loads(payload)
            if not isinstance(values, dict):
                raise ValueError
            return cls(
                expression=str(values["expression"]),
                light_color=str(values["light_color"]),
                light_animation=str(values["light_animation"]),
                sound_cue=str(values["sound_cue"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid reaction command payload.") from exc


_REACTION_COMMANDS = {
    ConversationReaction.CALM: ReactionCommand(
        "neutral", "soft-blue", "steady", "none"
    ),
    ConversationReaction.CURIOUS: ReactionCommand(
        "attentive", "cyan", "breathe", "thinking"
    ),
    ConversationReaction.WARM: ReactionCommand(
        "smile", "warm-white", "breathe", "none"
    ),
    ConversationReaction.CONFUSED: ReactionCommand(
        "puzzled", "amber", "pulse", "confused"
    ),
    ConversationReaction.CAUTIOUS: ReactionCommand(
        "alert", "red", "blink", "warning"
    ),
    ConversationReaction.HAPPY: ReactionCommand(
        "big-smile", "green", "sparkle", "success"
    ),
}


def reaction_command_for(event: ConversationEvent) -> ReactionCommand:
    if event.phase is ConversationPhase.STOPPED:
        return ReactionCommand("resting", "off", "steady", "none")
    if event.phase is ConversationPhase.WAITING:
        return ReactionCommand("attentive", "soft-blue", "breathe", "none")
    return _REACTION_COMMANDS[event.reaction]


def conversation_event_from_json(payload: str) -> ConversationEvent:
    try:
        values = json.loads(payload)
        if not isinstance(values, dict):
            raise ValueError
        return ConversationEvent(
            phase=ConversationPhase(values["phase"]),
            reaction=ConversationReaction(values["reaction"]),
            reason=str(values["reason"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid conversation event payload.") from exc
