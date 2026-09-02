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
    priority: int = 0
    minimum_duration_ms: int = 0

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
                priority=max(0, int(values.get("priority", 0))),
                minimum_duration_ms=max(
                    0,
                    int(values.get("minimum_duration_ms", 0)),
                ),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid reaction command payload.") from exc


_REACTION_COMMANDS = {
    ConversationReaction.CALM: ReactionCommand(
        "neutral", "soft-blue", "steady", "none", 10, 200
    ),
    ConversationReaction.CURIOUS: ReactionCommand(
        "attentive", "cyan", "breathe", "thinking", 30, 500
    ),
    ConversationReaction.WARM: ReactionCommand(
        "smile", "warm-white", "breathe", "none", 20, 600
    ),
    ConversationReaction.CONFUSED: ReactionCommand(
        "puzzled", "amber", "pulse", "confused", 40, 800
    ),
    ConversationReaction.CAUTIOUS: ReactionCommand(
        "alert", "red", "blink", "warning", 100, 1200
    ),
    ConversationReaction.HAPPY: ReactionCommand(
        "big-smile", "green", "sparkle", "success", 50, 1000
    ),
}


def reaction_command_for(event: ConversationEvent) -> ReactionCommand:
    if event.phase is ConversationPhase.STOPPED:
        return ReactionCommand("resting", "off", "steady", "none", 100, 0)
    if event.phase is ConversationPhase.WAITING:
        return ReactionCommand(
            "attentive", "soft-blue", "breathe", "none", 10, 500
        )
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
