from __future__ import annotations

from array import array
from collections.abc import Callable
from enum import Enum
import os
from pathlib import Path
import subprocess
import sys
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


class PorcupineWakeWordTrigger:
    name = "wakeword"

    def __init__(
        self,
        *,
        device: str = "default",
        keyword_path: Path | None = None,
        model_path: Path | None = None,
        sensitivity: float = 0.5,
        access_key: str | None = None,
        engine: Any | None = None,
        process_factory: Callable[..., Any] = subprocess.Popen,
    ) -> None:
        if not 0.0 <= sensitivity <= 1.0:
            raise ValueError("wake word sensitivity must be between 0.0 and 1.0")
        if engine is None:
            access_key = access_key or os.environ.get("PICOVOICE_ACCESS_KEY")
            if not access_key:
                raise RuntimeError(
                    "PICOVOICE_ACCESS_KEY is not set. Export it before using "
                    "the wake word trigger."
                )
            if keyword_path is None:
                raise RuntimeError(
                    "--wake-word-model is required for the wake word trigger."
                )
            if model_path is None:
                raise RuntimeError(
                    "--wake-word-language-model is required for Japanese wake words."
                )
            keyword_path = keyword_path.expanduser().resolve()
            model_path = model_path.expanduser().resolve()
            if not keyword_path.is_file():
                raise RuntimeError(f"Wake word model not found: {keyword_path}")
            if not model_path.is_file():
                raise RuntimeError(f"Porcupine language model not found: {model_path}")
            try:
                import pvporcupine
            except ImportError as exc:
                raise RuntimeError(
                    "pvporcupine is required. Activate .venv and run: "
                    "python -m pip install -r requirements-phase3.txt"
                ) from exc
            engine = pvporcupine.create(
                access_key=access_key,
                keyword_paths=[str(keyword_path)],
                model_path=str(model_path),
                sensitivities=[sensitivity],
            )
        self.device = device
        self._engine = engine
        self._process_factory = process_factory

    def wait(self) -> bool:
        if self._engine is None:
            raise RuntimeError("Wake word trigger is already closed.")
        frame_bytes = self._engine.frame_length * 2
        command = [
            "arecord",
            "--quiet",
            "-D",
            self.device,
            "-c",
            "1",
            "-f",
            "S16_LE",
            "-r",
            str(self._engine.sample_rate),
            "-t",
            "raw",
        ]
        process = self._process_factory(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        try:
            if process.stdout is None:
                raise RuntimeError("arecord did not provide an audio stream")
            while True:
                chunk = process.stdout.read(frame_bytes)
                if len(chunk) != frame_bytes:
                    raise RuntimeError("arecord stopped while waiting for wake word")
                samples = array("h")
                samples.frombytes(chunk)
                if sys.byteorder != "little":
                    samples.byteswap()
                if self._engine.process(samples.tolist()) >= 0:
                    return True
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

    def close(self) -> None:
        if self._engine is not None:
            self._engine.delete()
            self._engine = None


def create_start_trigger(
    backend: str,
    *,
    button_pin: int = DEFAULT_CONVERSATION_BUTTON_PIN,
    wake_word_device: str = "default",
    wake_word_model: Path | None = None,
    wake_word_language_model: Path | None = None,
    wake_word_sensitivity: float = 0.5,
) -> StartTrigger:
    if backend == "keyboard":
        return KeyboardStartTrigger()
    if backend == "gpio":
        return GpioButtonStartTrigger(button_pin)
    if backend == "wakeword":
        return PorcupineWakeWordTrigger(
            device=wake_word_device,
            keyword_path=wake_word_model,
            model_path=wake_word_language_model,
            sensitivity=wake_word_sensitivity,
        )
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
