from __future__ import annotations

from collections.abc import Callable
from enum import Enum
import json
from pathlib import Path
import subprocess
import time
from typing import Any, Protocol


DEFAULT_CONVERSATION_BUTTON_PIN = 17
DEFAULT_WAKE_PHRASE = "ねえ バディ"
DEFAULT_WAKE_WORD_REARM_DELAY = 1.5


class InteractionState(str, Enum):
    WAITING = "waiting"
    CONVERSATION = "conversation"
    STOPPED = "stopped"


class TriggerActivation(str, Enum):
    USER = "user"
    PROACTIVE = "proactive"


def is_active_hour(hour: int, start_hour: int, end_hour: int) -> bool:
    """Return whether an hour is inside a daily window, including overnight."""
    if not all(0 <= value <= 23 for value in (hour, start_hour, end_hour)):
        raise ValueError("active hours must be between 0 and 23")
    if start_hour == end_hour:
        return True
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


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


def normalize_wake_phrase(text: str) -> str:
    return "".join(
        character for character in text.casefold() if character.isalnum()
    )


def wake_phrase_detected(payload: str, targets: tuple[str, ...]) -> bool:
    try:
        result = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(result, dict):
        return False
    text = result.get("partial") or result.get("text") or ""
    normalized = normalize_wake_phrase(str(text))
    return bool(normalized) and normalized in targets


class VoskWakeWordTrigger:
    name = "wakeword"

    def __init__(
        self,
        *,
        device: str = "default",
        model_path: Path | None = None,
        phrase: str = DEFAULT_WAKE_PHRASE,
        sample_rate: int = 16000,
        chunk_duration: float = 0.1,
        proactive_interval: float = 0.0,
        proactive_allowed: Callable[[], bool] | None = None,
        recognizer: Any | None = None,
        process_factory: Callable[..., Any] = subprocess.Popen,
    ) -> None:
        phrase = phrase.strip()
        if not phrase:
            raise ValueError("wake word phrase must not be empty")
        if sample_rate <= 0:
            raise ValueError("wake word sample rate must be greater than zero")
        if chunk_duration <= 0:
            raise ValueError("wake word chunk duration must be greater than zero")

        self._model: Any | None = None
        if recognizer is None:
            if model_path is None:
                raise RuntimeError(
                    "--wake-word-model is required for the wake word trigger."
                )
            model_path = model_path.expanduser().resolve()
            if not model_path.is_dir():
                raise RuntimeError(f"Vosk model directory not found: {model_path}")
            try:
                import vosk
            except ImportError as exc:
                raise RuntimeError(
                    "vosk is required. Activate .venv and run: "
                    "python -m pip install -r requirements-phase3.txt"
                ) from exc
            vosk.SetLogLevel(-1)
            self._model = vosk.Model(str(model_path))
            phrase_words = tuple(phrase.split())
            grammar_phrases = list(
                dict.fromkeys((phrase, *phrase_words, "[unk]"))
            )
            grammar = json.dumps(grammar_phrases, ensure_ascii=False)
            recognizer = vosk.KaldiRecognizer(
                self._model,
                sample_rate,
                grammar,
            )

        self.device = device
        self.phrase = phrase
        self.sample_rate = sample_rate
        self._chunk_bytes = max(1, round(sample_rate * chunk_duration)) * 2
        self._proactive_chunks = (
            0
            if proactive_interval <= 0
            else max(1, round(proactive_interval / chunk_duration))
        )
        self._proactive_allowed = proactive_allowed or (lambda: True)
        self._targets = (normalize_wake_phrase(phrase),)
        self._recognizer = recognizer
        self._process_factory = process_factory
        self.activation = TriggerActivation.USER

    def wait(self) -> bool:
        if self._recognizer is None:
            raise RuntimeError("Wake word trigger is already closed.")
        self._recognizer.Reset()
        chunks_waited = 0
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
            str(self.sample_rate),
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
                chunk = process.stdout.read(self._chunk_bytes)
                if len(chunk) != self._chunk_bytes:
                    raise RuntimeError("arecord stopped while waiting for wake word")
                completed = self._recognizer.AcceptWaveform(chunk)
                chunks_waited += 1
                if completed:
                    payload = self._recognizer.Result()
                    if wake_phrase_detected(payload, self._targets):
                        self.activation = TriggerActivation.USER
                        return True
                if (
                    self._proactive_chunks > 0
                    and chunks_waited >= self._proactive_chunks
                ):
                    chunks_waited = 0
                    if self._proactive_allowed():
                        self.activation = TriggerActivation.PROACTIVE
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
        self._recognizer = None
        self._model = None


def create_start_trigger(
    backend: str,
    *,
    button_pin: int = DEFAULT_CONVERSATION_BUTTON_PIN,
    wake_word_device: str = "default",
    wake_word_model: Path | None = None,
    wake_phrase: str = DEFAULT_WAKE_PHRASE,
    proactive_interval: float = 0.0,
    proactive_allowed: Callable[[], bool] | None = None,
) -> StartTrigger:
    if backend == "keyboard":
        return KeyboardStartTrigger()
    if backend == "gpio":
        return GpioButtonStartTrigger(button_pin)
    if backend == "wakeword":
        return VoskWakeWordTrigger(
            device=wake_word_device,
            model_path=wake_word_model,
            phrase=wake_phrase,
            proactive_interval=proactive_interval,
            proactive_allowed=proactive_allowed,
        )
    raise ValueError(f"Unknown start trigger: {backend}")


def run_interaction_station(
    *,
    trigger: StartTrigger,
    run_session: Callable[[], int],
    sessions: int = 0,
    rearm_delay: float = 0.0,
    reset_session: Callable[[], None] | None = None,
    on_state_change: Callable[[InteractionState], None] | None = None,
    output: Callable[[str], None] = print,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    """Run triggered conversation sessions; zero sessions means no fixed limit."""
    if sessions < 0:
        raise ValueError("sessions must be 0 or greater")
    if rearm_delay < 0:
        raise ValueError("rearm delay must be 0 or greater")

    completed_sessions = 0
    try:
        while sessions == 0 or completed_sessions < sessions:
            if on_state_change is not None:
                on_state_change(InteractionState.WAITING)
            output(
                f"state={InteractionState.WAITING.value} trigger={trigger.name}"
            )
            if not trigger.wait():
                break

            session = completed_sessions + 1
            if reset_session is not None:
                reset_session()
            if on_state_change is not None:
                on_state_change(InteractionState.CONVERSATION)
            output(
                f"state={InteractionState.CONVERSATION.value} session={session}"
            )
            completed_turns = run_session()
            completed_sessions += 1
            output(
                f"state={InteractionState.WAITING.value} session={session} "
                f"completed-turns={completed_turns}"
            )
            more_sessions = sessions == 0 or completed_sessions < sessions
            if more_sessions and rearm_delay > 0:
                output(f"state=cooldown duration={rearm_delay:.1f}s")
                sleeper(rearm_delay)
    except KeyboardInterrupt:
        output("Stopping interaction station.")
    finally:
        trigger.close()
        if on_state_change is not None:
            on_state_change(InteractionState.STOPPED)
        output(f"state={InteractionState.STOPPED.value}")
    return completed_sessions
