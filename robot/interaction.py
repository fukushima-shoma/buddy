from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any, Protocol


DEFAULT_CONVERSATION_BUTTON_PIN = 17


class InteractionState(str, Enum):
    WAITING = "waiting"
    CONVERSATION = "conversation"
    STOPPED = "stopped"


class StartTrigger(Protocol):
    name: str

    def wait(self) -> bool:
        """Wait for a start request, returning False when the station should stop."""

    def close(self) -> None:
        """Release resources held by the trigger."""


class KeyboardStartTrigger:
    name = "keyboard"

    def __init__(self, input_fn: Callable[[str], str] = input) -> None:
        self._input = input_fn

    def wait(self) -> bool:
        try:
            value = self._input(
                "Press Enter to start a conversation (q + Enter to quit): "
            )
        except EOFError:
            return False
        return value.strip().lower() != "q"

    def close(self) -> None:
        return None


class GpioButtonStartTrigger:
    name = "gpio"

    def __init__(
        self,
        pin: int = DEFAULT_CONVERSATION_BUTTON_PIN,
        *,
        button: Any | None = None,
    ) -> None:
        if button is None:
            try:
                from gpiozero import Button
            except ImportError as exc:
                raise RuntimeError(
                    "gpiozero is required for the GPIO conversation button."
                ) from exc
            button = Button(pin, pull_up=True, bounce_time=0.1)
        self.pin = pin
        self._button = button

    def wait(self) -> bool:
        self._button.wait_for_press()
        self._button.wait_for_release()
        return True

    def close(self) -> None:
        self._button.close()


def create_start_trigger(
    backend: str,
    *,
    button_pin: int = DEFAULT_CONVERSATION_BUTTON_PIN,
) -> StartTrigger:
    if backend == "keyboard":
        return KeyboardStartTrigger()
    if backend == "gpio":
        return GpioButtonStartTrigger(button_pin)
    raise ValueError(f"Unknown start trigger: {backend}")


def run_interaction_station(
    *,
    trigger: StartTrigger,
    run_session: Callable[[], int],
    sessions: int = 0,
    reset_session: Callable[[], None] | None = None,
    output: Callable[[str], None] = print,
) -> int:
    """Run triggered conversation sessions; zero sessions means no fixed limit."""
    if sessions < 0:
        raise ValueError("sessions must be 0 or greater")

    completed_sessions = 0
    try:
        while sessions == 0 or completed_sessions < sessions:
            output(
                f"state={InteractionState.WAITING.value} trigger={trigger.name}"
            )
            if not trigger.wait():
                break

            session = completed_sessions + 1
            if reset_session is not None:
                reset_session()
            output(
                f"state={InteractionState.CONVERSATION.value} session={session}"
            )
            completed_turns = run_session()
            completed_sessions += 1
            output(
                f"state={InteractionState.WAITING.value} session={session} "
                f"completed-turns={completed_turns}"
            )
    except KeyboardInterrupt:
        output("Stopping interaction station.")
    finally:
        trigger.close()
        output(f"state={InteractionState.STOPPED.value}")
    return completed_sessions
