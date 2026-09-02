from __future__ import annotations

import time
from typing import Callable, Protocol

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

    def __init__(
        self,
        driver: ReactionDriver,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.driver = driver
        self._clock = clock
        self.current: ReactionCommand | None = None
        self.pending: ReactionCommand | None = None
        self._hold_until = 0.0

    def apply(self, command: ReactionCommand) -> bool:
        if command == self.current:
            return False
        now = self._clock()
        if (
            self.current is not None
            and now < self._hold_until
            and command.priority < self.current.priority
        ):
            self.pending = command
            return False
        return self._apply_now(command, now)

    def tick(self) -> bool:
        now = self._clock()
        if self.pending is None or now < self._hold_until:
            return False
        command = self.pending
        self.pending = None
        return self._apply_now(command, now)

    def _apply_now(self, command: ReactionCommand, now: float) -> bool:
        self.driver.apply(command)
        self.current = command
        self.pending = None
        self._hold_until = now + command.minimum_duration_ms / 1000
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
        f"{command.light_animation} sound={command.sound_cue} "
        f"priority={command.priority} hold_ms={command.minimum_duration_ms}"
    )
