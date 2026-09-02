from __future__ import annotations

from typing import Protocol

from robot.reaction import ReactionCommand


FACES = {
    "neutral": "(•‿•)",
    "attentive": "(•̀ᴗ•́)",
    "smile": "(◕‿◕)",
    "puzzled": "(・_・?)",
    "alert": "(•̀o•́)",
    "big-smile": "(≧▽≦)",
    "resting": "(-‿-)",
}


class ReactionDriver(Protocol):
    def apply(self, command: ReactionCommand) -> None: ...


class ReactionOutputController:
    """Apply semantic reactions while suppressing duplicate driver writes."""

    def __init__(self, driver: ReactionDriver) -> None:
        self.driver = driver
        self.current: ReactionCommand | None = None

    def apply(self, command: ReactionCommand) -> bool:
        if command == self.current:
            return False
        self.driver.apply(command)
        self.current = command
        return True


class MockReactionDriver:
    def __init__(self) -> None:
        self.commands: list[ReactionCommand] = []

    def apply(self, command: ReactionCommand) -> None:
        self.commands.append(command)


def render_reaction(command: ReactionCommand) -> str:
    face = FACES.get(command.expression, FACES["neutral"])
    return (
        f"{face} expression={command.expression} light={command.light_color}/"
        f"{command.light_animation} sound={command.sound_cue}"
    )
