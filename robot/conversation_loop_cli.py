from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re
import time
from typing import Any, Callable
from uuid import uuid4

from robot.audio import (
    AlsaVoiceActivatedRecorder,
    AudioPlayer,
    AudioRecorder,
    NoSpeechDetectedError,
    generate_engine_rev,
)
from robot.audio_cli import create_player, create_recorder
from robot.buddy_identity import BUDDY_PROACTIVE_INVITATION
from robot.child_games import ChildGameController, is_game_end_transcript
from robot.conversation import (
    DEFAULT_MEMORY_TURNS,
    DEFAULT_REPLY_MODEL,
    DEFAULT_REPLY_REASONING_EFFORT,
    ReplyGenerator,
)
from robot.conversation_memory import (
    DEFAULT_CONVERSATION_MEMORY_PATH,
    ConversationMemoryStore,
)
from robot.conversation_state import (
    ConversationEvent,
    ConversationEventHandler,
    ConversationPhase,
    ConversationReaction,
    ConversationStateTracker,
)
from robot.conversation_intents import (
    CHILD_RETRY_REPLIES,
    DEFAULT_RETRY_REPLIES,
    DEFAULT_FAREWELL_REPLY,
    DEFAULT_INACTIVITY_REPLY,
    LocalShortReply,
    LocalShortReplyController,
    MOBILITY_ALREADY_RUNNING_REPLY,
    MOBILITY_ALREADY_STOPPED_REPLY,
    MOBILITY_CANCEL_REPLY,
    MOBILITY_CLARIFY_REPLY,
    MOBILITY_CONFIRM_AGAIN_REPLY,
    MOBILITY_CONFIRM_REPLY,
    MOBILITY_FAREWELL_REPLY,
    MOBILITY_START_REPLY,
    MOBILITY_STOP_REPLY,
    MOBILITY_UNAVAILABLE_REPLY,
    NOTHING_TO_REPEAT_REPLY,
    POWER_GOOD_REPLY,
    POWER_LOW_REPLY,
    POWER_UNAVAILABLE_REPLY,
    is_ambiguous_mobility_transcript,
    is_farewell_transcript,
    is_mobility_cancel_transcript,
    is_mobility_confirm_transcript,
    is_mobility_start_transcript,
    is_mobility_stop_transcript,
    is_power_status_transcript,
    is_repeat_reply_transcript,
)
from robot.interaction import (
    DEFAULT_CONVERSATION_BUTTON_PIN,
    DEFAULT_WAKE_PHRASE,
    DEFAULT_WAKE_WORD_REARM_DELAY,
    InteractionState,
    TriggerActivation,
    create_start_trigger,
    is_active_hour,
    run_interaction_station,
)
from robot.mobility import PersonFollowProcessController, Ros2FollowController
from robot.profile_memory import DEFAULT_PROFILE_MEMORY_PATH, ParentManagedMemory
from robot.power import RaspberryPiPowerMonitor
from robot.reply_cli import create_reply_generator
from robot.realtime_conversation import (
    DEFAULT_REALTIME_MODEL,
    DEFAULT_REALTIME_TIMEOUT,
    REALTIME_SAMPLE_RATE,
    RealtimeConversation,
)
from robot.speech import (
    DEFAULT_SPEECH_CHUNK_BYTES,
    SPEECH_CHUNK_SIZES,
    DEFAULT_SPEECH_MODEL,
    DEFAULT_SPEECH_SPEED,
    DEFAULT_SPEECH_STYLE,
    DEFAULT_SPEECH_VOICE,
    SPEECH_STYLES,
    SpeechSynthesizer,
)
from robot.speech_cli import create_synthesizer
from robot.shared_experience_memory import (
    DEFAULT_SHARED_EXPERIENCE_PATH,
    SharedExperienceStore,
    SpokenSharedExperienceMemory,
)
from robot.spoken_profile_memory import SpokenProfileMemory
from robot.transcribe_cli import create_transcriber
from robot.transcription import (
    CHILD_TRANSCRIPTION_PROMPT,
    DEFAULT_TRANSCRIPTION_MODEL,
    Transcriber,
    is_unreliable_child_transcript,
    is_unreliable_transcript,
)


DEFAULT_MAX_SILENCE_TURNS = 2
PROACTIVE_INVITATION = BUDDY_PROACTIVE_INVITATION


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Repeat Buddy's record, reply, and playback cycle."
    )
    parser.add_argument(
        "--audio-backend", choices=("mock", "alsa", "alsa-vad"), default="mock"
    )
    parser.add_argument("--audio-device", default="default")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("captures/audio/conversation-input.wav"),
    )
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--speech-threshold", type=float, default=500.0)
    parser.add_argument("--silence-duration", type=float, default=0.8)
    parser.add_argument("--semantic-silence-duration", type=float, default=3.0,
                        help="Fallback after this much continuous quiet if semantic VAD keeps waiting.")
    parser.add_argument("--max-wait", type=float, default=10.0)
    parser.add_argument("--pre-roll", type=float, default=0.3)
    parser.add_argument(
        "--transcription-backend", choices=("mock", "openai"), default="mock"
    )
    parser.add_argument("--transcription-model", default=DEFAULT_TRANSCRIPTION_MODEL)
    parser.add_argument("--language", default="ja")
    parser.add_argument(
        "--transcription-prompt",
        help="Optional context hint passed to the transcription model.",
    )
    parser.add_argument("--mock-text", default="こんにちは、Buddy")
    parser.add_argument(
        "--reply-backend", choices=("mock", "openai"), default="mock"
    )
    parser.add_argument(
        "--conversation-backend", choices=("pipeline", "realtime"), default="pipeline",
        help="Use Realtime audio replies with the existing pipeline as fallback.",
    )
    parser.add_argument("--realtime-model", default=DEFAULT_REALTIME_MODEL)
    parser.add_argument("--realtime-timeout", type=float, default=DEFAULT_REALTIME_TIMEOUT)
    parser.add_argument("--realtime-turn-detection", choices=("manual", "semantic"), default="manual")
    parser.add_argument("--semantic-eagerness", choices=("low", "medium", "high", "auto"),
                        default="medium", help="Semantic end-of-turn responsiveness.")
    parser.add_argument("--empty-commit-grace", type=float, default=1.0,
                        help="Seconds to wait for a commit confirmation after an empty-buffer race.")
    parser.add_argument("--reply-model", default=DEFAULT_REPLY_MODEL)
    parser.add_argument(
        "--reply-reasoning-effort",
        choices=("none", "low", "medium", "high", "xhigh", "max"),
        default=DEFAULT_REPLY_REASONING_EFFORT,
    )
    parser.add_argument("--mock-reply", default="こんにちは！今日は何をして遊ぶ？")
    parser.add_argument(
        "--child-mode",
        action="store_true",
        help="Use supervised, age-appropriate replies and recognition retries.",
    )
    parser.add_argument(
        "--child-games",
        action="store_true",
        help="Enable deterministic riddles, animal quizzes, and vehicle quizzes.",
    )
    parser.add_argument(
        "--local-short-replies",
        action="store_true",
        help="Answer safe exact short phrases locally without a reply API call.",
    )
    parser.add_argument(
        "--memory",
        choices=("none", "session", "persistent"),
        default="none",
        help=(
            "Use no context, session context, or session context with indexed "
            "recall of related past conversations."
        ),
    )
    parser.add_argument(
        "--memory-turns",
        type=int,
        default=DEFAULT_MEMORY_TURNS,
        help="Reset session context after this many replies.",
    )
    parser.add_argument(
        "--profile-memory",
        type=Path,
        default=DEFAULT_PROFILE_MEMORY_PATH,
        help="Parent-managed local profile memory JSON file.",
    )
    parser.add_argument(
        "--auto-conversation-memory",
        action="store_true",
        help="Persist conversation text locally for later sessions.",
    )
    parser.add_argument(
        "--conversation-memory-file",
        type=Path,
        default=DEFAULT_CONVERSATION_MEMORY_PATH,
    )
    parser.add_argument(
        "--shared-experience-memory",
        action="store_true",
        help="Persist explicit shared experiences until they are deleted.",
    )
    parser.add_argument(
        "--shared-experience-memory-file",
        type=Path,
        default=DEFAULT_SHARED_EXPERIENCE_PATH,
    )
    parser.add_argument(
        "--mobility-backend",
        choices=("off", "person-follow", "ros2-follow"),
        default="off",
        help="Allow exact spoken commands to start and stop person following.",
    )
    parser.add_argument(
        "--conversation-events",
        choices=("off", "ros2"),
        default="off",
        help="Publish conversation state and reactions through ROS 2.",
    )
    parser.add_argument("--conversation-display", action="store_true",
                        help="Serve a read-only conversation screen for a browser.")
    parser.add_argument("--conversation-display-host", default="127.0.0.1")
    parser.add_argument("--conversation-display-port", type=int, default=8765)
    parser.add_argument("--mobility-speed", type=float, default=1.0)
    parser.add_argument("--mobility-stop-distance", type=float, default=60.0)
    parser.add_argument("--mobility-resume-distance", type=float, default=70.0)
    parser.add_argument("--mobility-turn-pulse", type=float, default=0.08)
    parser.add_argument(
        "--power-monitor",
        choices=("off", "raspberry-pi"),
        default="off",
        help="Block or stop movement on Raspberry Pi undervoltage.",
    )
    parser.add_argument(
        "--speech-backend", choices=("mock", "openai"), default="mock"
    )
    parser.add_argument("--speech-model", default=DEFAULT_SPEECH_MODEL)
    parser.add_argument("--speech-voice", default=DEFAULT_SPEECH_VOICE)
    parser.add_argument(
        "--speech-style", choices=SPEECH_STYLES, default=DEFAULT_SPEECH_STYLE
    )
    parser.add_argument("--speech-speed", type=float, default=DEFAULT_SPEECH_SPEED)
    parser.add_argument("--speech-chunk-bytes", type=int, choices=SPEECH_CHUNK_SIZES,
                        default=DEFAULT_SPEECH_CHUNK_BYTES)
    parser.add_argument("--fixed-speech-cache", type=Path, default=None,
                        help="Read prepared fixed phrases from this directory (disabled by default).")
    parser.add_argument(
        "--speech-output",
        type=Path,
        default=Path("captures/audio/conversation-reply.wav"),
    )
    parser.add_argument(
        "--playback-backend",
        choices=("mock", "alsa", "alsa-interruptible"),
        default="mock",
    )
    parser.add_argument("--playback-device", default="default")
    parser.add_argument(
        "--barge-in-threshold",
        type=float,
        default=2500.0,
        help="Microphone RMS needed to interrupt alsa-interruptible playback.",
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=1,
        help="Number of turns; use 0 to continue until Ctrl+C.",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.5,
        help="Seconds to wait after playback before the next recording.",
    )
    parser.add_argument(
        "--max-silence-turns",
        type=int,
        default=DEFAULT_MAX_SILENCE_TURNS,
        help="End a session after this many silent turns; use 0 to disable.",
    )
    parser.add_argument(
        "--start-trigger",
        choices=("immediate", "keyboard", "gpio", "wakeword"),
        default="immediate",
        help="Start immediately, after Enter, a GPIO press, or a wake word.",
    )
    parser.add_argument(
        "--button-pin",
        type=int,
        default=DEFAULT_CONVERSATION_BUTTON_PIN,
        help="BCM GPIO number used by the conversation button.",
    )
    parser.add_argument(
        "--sessions",
        type=int,
        default=0,
        help="Triggered sessions to run; use 0 to wait until q or Ctrl+C.",
    )
    parser.add_argument(
        "--wake-word-model",
        type=Path,
        help="Path to the extracted Japanese Vosk model directory.",
    )
    parser.add_argument(
        "--wake-phrase",
        default=DEFAULT_WAKE_PHRASE,
        help=f"Local wake phrase (default: {DEFAULT_WAKE_PHRASE}).",
    )
    parser.add_argument(
        "--wake-word-device",
        help="ALSA capture device; defaults to --audio-device.",
    )
    parser.add_argument(
        "--wake-word-rearm-delay",
        type=float,
        default=DEFAULT_WAKE_WORD_REARM_DELAY,
        help=(
            "Seconds to ignore playback echo after a wake-word session "
            f"(default: {DEFAULT_WAKE_WORD_REARM_DELAY})."
        ),
    )
    parser.add_argument(
        "--proactive-interval",
        type=float,
        default=0.0,
        help="Idle seconds before Buddy invites a conversation; 0 disables it.",
    )
    parser.add_argument(
        "--proactive-start-hour",
        type=int,
        choices=range(24),
        default=8,
    )
    parser.add_argument(
        "--proactive-end-hour",
        type=int,
        choices=range(24),
        default=20,
    )
    parser.add_argument(
        "--orientation-backend",
        choices=("off", "mock", "gpiozero"),
        default="off",
        help="Optionally turn toward a detected person before recording.",
    )
    parser.add_argument("--orientation-speed", type=float, default=1.0)
    parser.add_argument("--orientation-pulse", type=float, default=0.12)
    parser.add_argument("--orientation-attempts", type=int, default=4)
    parser.add_argument(
        "--person-model",
        type=Path,
        default=Path("models/person_detection/person_detection_mediapipe_2023mar.onnx"),
    )
    parser.add_argument(
        "--person-model-helper",
        type=Path,
        default=Path("models/person_detection/mp_persondet.py"),
    )
    return parser


def run_conversation_loop(
    *,
    recorder: AudioRecorder,
    transcriber: Transcriber,
    reply_generator: ReplyGenerator,
    synthesizer: SpeechSynthesizer,
    player: AudioPlayer,
    input_path: Path,
    speech_output: Path,
    duration: float,
    sample_rate: int,
    language: str,
    turns: int,
    pause: float,
    retry_replies: tuple[str, ...] = (),
    farewell_reply: str = DEFAULT_FAREWELL_REPLY,
    max_silence_turns: int = DEFAULT_MAX_SILENCE_TURNS,
    inactivity_reply: str = DEFAULT_INACTIVITY_REPLY,
    on_exchange: Callable[[str, str], None] | None = None,
    start_mobility: Callable[[], bool] | None = None,
    stop_mobility: Callable[[], bool] | None = None,
    mobility_active: Callable[[], bool] | None = None,
    power_good: Callable[[], bool] | None = None,
    handle_child_game: Callable[[str], str | None] | None = None,
    child_game_active: Callable[[], bool] | None = None,
    handle_profile_memory: Callable[[str], str | None] | None = None,
    handle_shared_experience: Callable[[str], str | None] | None = None,
    handle_local_short_reply: Callable[[str], LocalShortReply | None] | None = None,
    on_conversation_event: ConversationEventHandler | None = None,
    on_transcript: Callable[[str | None], None] | None = None,
    reject_transcript: Callable[[str], bool] | None = None,
    output: Callable[[str], None] = print,
    sleeper: Callable[[float], None] = time.sleep,
    catch_interrupt: bool = True,
    clock: Callable[[], float] = time.monotonic,
    realtime: RealtimeConversation | None = None,
) -> int:
    if turns < 0:
        raise ValueError("turns must be 0 or greater")
    if max_silence_turns < 0:
        raise ValueError("max silence turns must be 0 or greater")
    if realtime is not None and sample_rate != REALTIME_SAMPLE_RATE:
        raise ValueError("Realtime requires --sample-rate 24000.")

    completed_turns = 0
    recognition_failures = 0
    consecutive_silences = 0
    mobility_confirmation_pending = False
    last_spoken_source: Path | None = None
    state = ConversationStateTracker(on_conversation_event)

    recorded_at: float | None = None
    playback_ended_at: float | None = None
    reply_interrupted = False

    def synthesize_reply(text: str, destination: Path) -> Path:
        if realtime is not None:
            realtime.discard_pending()
        started = clock()
        result = synthesizer.synthesize(text, destination)
        log_speech_settings()
        cache_hit = getattr(synthesizer, "last_cache_hit", False)
        output(
            f"turn={turn} timing=synthesis seconds={clock() - started:.3f} "
            f"cached={str(cache_hit).lower()}"
        )
        return result

    def log_speech_settings() -> None:
        output(
            f"turn={turn} speech-output chunk-bytes={getattr(synthesizer, 'chunk_bytes', 0)} "
            f"cache-source={getattr(synthesizer, 'last_cache_source', 'none')}"
        )

    def play_with_stop_interrupt(
        source: Path,
        turn: int,
        reaction: ConversationReaction = ConversationReaction.WARM,
        reason: str = "reply",
    ) -> None:
        nonlocal last_spoken_source, reply_interrupted
        last_spoken_source = source
        state.transition(
            ConversationPhase.SPEAKING,
            reaction,
            reason,
        )
        if recorded_at is not None:
            output(
                f"turn={turn} timing=recording-to-playback "
                f"seconds={clock() - recorded_at:.3f} "
                f"path={'pipeline' if reason == 'reply' else 'local' if reason == 'local-short-reply' else 'control'}"
            )
        player.play(source)
        reply_interrupted = reply_interrupted or bool(getattr(player, "last_interrupted", False))

        handle_playback_stop(turn)

    def handle_playback_stop(turn: int) -> None:
        nonlocal last_spoken_source, reply_interrupted, playback_ended_at
        playback_ended_at = clock()
        state.transition(
            ConversationPhase.THINKING,
            ConversationReaction.CURIOUS,
            "playback-ended",
        )
        consume_stop = getattr(player, "consume_stop_request", None)
        if not callable(consume_stop) or not consume_stop():
            return
        reply_interrupted = True
        stopped = stop_mobility() if stop_mobility is not None else False
        output(
            f"turn={turn} mobility={'stopped' if stopped else 'already-stopped'} "
            "reason=local-voice-interrupt"
        )
        confirmation = (
            MOBILITY_STOP_REPLY if stopped else MOBILITY_ALREADY_STOPPED_REPLY
        )
        generated = synthesize_reply(confirmation, speech_output)
        output(f"turn={turn} interrupt-reply={confirmation}")
        output(f"turn={turn} interrupt-synthesized={generated}")
        last_spoken_source = generated
        state.transition(
            ConversationPhase.SPEAKING,
            ConversationReaction.CAUTIOUS,
            "local-voice-interrupt",
        )
        player.play(generated)
        state.transition(
            ConversationPhase.THINKING,
            ConversationReaction.CURIOUS,
            "playback-ended",
        )
        consume_stop()
        output(f"turn={turn} interrupt-played={generated}")

    def stream_and_play_reply(
        text: str,
        destination: Path,
        reaction: ConversationReaction = ConversationReaction.WARM,
        reason: str = "reply",
    ) -> Path | None:
        nonlocal last_spoken_source, reply_interrupted
        stream_speech = getattr(synthesizer, "stream", None)
        play_stream = getattr(player, "play_stream", None)
        if not callable(stream_speech) or not callable(play_stream):
            return None

        started = clock()
        chunks = iter(stream_speech(text, destination))
        try:
            first_chunk = next(chunks)
        except StopIteration as exc:
            raise RuntimeError("speech stream did not contain audio") from exc

        last_spoken_source = destination
        elapsed = clock() - started
        log_speech_settings()
        output(
            f"turn={turn} timing=synthesis-first-audio seconds={elapsed:.3f} "
            f"cached={str(getattr(synthesizer, 'last_cache_hit', False)).lower()}"
        )
        state.transition(ConversationPhase.SPEAKING, reaction, reason)
        if recorded_at is not None:
            output(
                f"turn={turn} timing=recording-to-playback "
                f"seconds={clock() - recorded_at:.3f} streaming=true "
                f"path={'local' if reason == 'local-short-reply' else 'pipeline'}"
            )

        def replay_chunks():
            try:
                yield first_chunk
                yield from chunks
            finally:
                close_stream = getattr(chunks, "close", None)
                if callable(close_stream):
                    close_stream()

        play_stream(replay_chunks())
        reply_interrupted = reply_interrupted or bool(getattr(player, "last_interrupted", False))
        output(
            f"turn={turn} timing=streaming-playback-complete "
            f"seconds={clock() - started:.3f}"
        )
        handle_playback_stop(turn)
        return destination

    def read_power_good(turn: int) -> bool | None:
        if power_good is None:
            return None
        try:
            return power_good()
        except RuntimeError as exc:
            output(f"turn={turn} power=error detail={exc}")
            return None

    try:
        while turns == 0 or completed_turns < turns:
            if completed_turns > 0 and pause > 0:
                sleeper(pause)
            turn = completed_turns + 1
            recorded_at = None
            reply_interrupted = False
            realtime_input_available = realtime is not None
            if mobility_active is not None and mobility_active():
                power_state = read_power_good(turn)
                if power_good is not None and power_state is not True:
                    if stop_mobility is not None:
                        stop_mobility()
                    reply = (
                        POWER_LOW_REPLY
                        if power_state is False
                        else POWER_UNAVAILABLE_REPLY
                    )
                    output(f"turn={turn} reply={reply} reason=power-safety-stop")
                    generated = synthesize_reply(reply, speech_output)
                    output(f"turn={turn} synthesized={generated}")
                    play_with_stop_interrupt(
                        generated,
                        turn,
                        ConversationReaction.CAUTIOUS,
                        "power-safety-stop",
                    )
                    output(f"turn={turn} played={generated}")
                    completed_turns += 1
                    continue
            try:
                streaming_capture = False
                record_streaming = getattr(recorder, "record_streaming", None)
                if isinstance(recorder, AlsaVoiceActivatedRecorder) or (
                    realtime is not None and callable(record_streaming)
                ):
                    state.transition(
                        ConversationPhase.THINKING,
                        ConversationReaction.CURIOUS,
                        "preparing-audio",
                    )
                if realtime is not None and callable(record_streaming):
                    try:
                        realtime.begin_audio(language)
                        streaming_capture = True
                    except RuntimeError as exc:
                        output(f"turn={turn} realtime=fallback stage=connect detail={exc}")
                        realtime_input_available = False
                def microphone_ready() -> None:
                    nonlocal playback_ended_at
                    if playback_ended_at is not None:
                        output(f"turn={turn} timing=playback-to-listening seconds={clock() - playback_ended_at:.3f}")
                        playback_ended_at = None
                    output(f"turn={turn} listening=true")
                    state.transition(
                        ConversationPhase.LISTENING,
                        ConversationReaction.CALM,
                        "awaiting-speech",
                    )

                capture_options: dict[str, Any] = {}
                if isinstance(recorder, AlsaVoiceActivatedRecorder):
                    capture_options["on_ready"] = microphone_ready
                else:
                    microphone_ready()
                if streaming_capture:
                    capture_options["on_chunk"] = realtime.append_audio
                    if realtime.turn_detection == "semantic":
                        capture_options["should_stop"] = realtime.audio_turn_complete
                    source = record_streaming(
                        input_path, duration=duration, sample_rate=sample_rate,
                        **capture_options,
                    )
                else:
                    source = recorder.record(
                        input_path, duration=duration, sample_rate=sample_rate,
                        **capture_options,
                    )
            except NoSpeechDetectedError:
                state.transition(
                    ConversationPhase.THINKING,
                    ConversationReaction.CURIOUS,
                    "recording-ended",
                )
                output(f"turn={turn} transcript=not-found reason=no-speech")
                if mobility_active is not None and mobility_active():
                    output(f"turn={turn} mobility=running reason=no-speech")
                    consecutive_silences = 0
                    completed_turns += 1
                    continue
                consecutive_silences += 1
                if (
                    max_silence_turns > 0
                    and consecutive_silences >= max_silence_turns
                ):
                    output(
                        f"turn={turn} reply={inactivity_reply} "
                        "reason=conversation-ended-inactivity"
                    )
                    generated = synthesize_reply(
                        inactivity_reply,
                        speech_output,
                    )
                    output(f"turn={turn} synthesized={generated}")
                    play_with_stop_interrupt(generated, turn, reason="inactivity")
                    output(f"turn={turn} played={generated}")
                    completed_turns += 1
                    break
                if retry_replies:
                    retry = retry_replies[
                        min(recognition_failures, len(retry_replies) - 1)
                    ]
                    output(f"turn={turn} reply={retry} reason=no-speech")
                    generated = synthesize_reply(retry, speech_output)
                    output(f"turn={turn} synthesized={generated}")
                    play_with_stop_interrupt(
                        generated,
                        turn,
                        ConversationReaction.CONFUSED,
                        "no-speech",
                    )
                    output(f"turn={turn} played={generated}")
                    recognition_failures += 1
                completed_turns += 1
                continue
            recorded_at = clock()
            state.transition(
                ConversationPhase.THINKING,
                ConversationReaction.CURIOUS,
                "recording-ended",
            )
            output(f"turn={turn} recorded={source}")
            if hasattr(recorder, "last_stop_reason"):
                output(f"turn={turn} input-end={recorder.last_stop_reason} "
                       f"captured-seconds={recorder.last_duration:.3f} "
                       f"silence-seconds={recorder.last_trailing_silence:.3f}")
            consecutive_silences = 0

            started = clock()
            realtime_input_attempted = realtime is not None and realtime_input_available
            if realtime_input_attempted:
                try:
                    transcript = (
                        realtime.commit_audio()
                        if streaming_capture
                        else realtime.transcribe(source, language=language)
                    )
                except RuntimeError as exc:
                    output(f"turn={turn} realtime=fallback stage=transcription detail={exc}")
                    realtime_input_available = False
                    realtime.close()
                    transcript = transcriber.transcribe(source, language=language)
            else:
                transcript = transcriber.transcribe(source, language=language)
            if realtime_input_attempted and realtime is not None:
                diagnostic = realtime.input_diagnostics
                result = "success" if realtime_input_available else "fallback"
                output(
                    f"turn={turn} realtime=input result={result} "
                    f"failure={diagnostic['failure']} "
                    f"uploaded-bytes={diagnostic['uploaded_bytes']} "
                    f"manual-commit={str(diagnostic['manual_commit']).lower()} "
                    f"server-committed={str(diagnostic['server_committed']).lower()} "
                    f"events={diagnostic['events']}"
                    f" event-times={diagnostic.get('event_times', 'none')}"
                )
            output(f"turn={turn} timing=transcription seconds={clock() - started:.3f}")
            output(f"turn={turn} transcript={transcript or 'not-found'}")

            # A recognized stop command must bypass all rejection and dialog state.
            if transcript and is_mobility_stop_transcript(transcript):
                mobility_confirmation_pending = False
                stopped = stop_mobility() if stop_mobility is not None else False
                if on_transcript is not None:
                    on_transcript(transcript)
                reply = (
                    MOBILITY_STOP_REPLY
                    if stopped
                    else MOBILITY_ALREADY_STOPPED_REPLY
                )
                reason = "mobility-stop" if stopped else "mobility-already-stopped"
                output(f"turn={turn} reply={reply} reason={reason}")
                generated = synthesize_reply(reply, speech_output)
                output(f"turn={turn} synthesized={generated}")
                play_with_stop_interrupt(
                    generated,
                    turn,
                    ConversationReaction.CAUTIOUS,
                    reason,
                )
                output(f"turn={turn} played={generated}")
                completed_turns += 1
                continue

            if on_transcript is not None:
                on_transcript(transcript)

            failure_reason: str | None = None
            if not transcript:
                failure_reason = "empty-transcript"
            elif reject_transcript is not None and reject_transcript(transcript):
                failure_reason = "uncertain-transcript"
            if failure_reason is not None:
                if retry_replies:
                    retry = retry_replies[
                        min(recognition_failures, len(retry_replies) - 1)
                    ]
                    output(f"turn={turn} reply={retry} reason={failure_reason}")
                    generated = synthesize_reply(retry, speech_output)
                    output(f"turn={turn} synthesized={generated}")
                    play_with_stop_interrupt(
                        generated,
                        turn,
                        ConversationReaction.CONFUSED,
                        failure_reason,
                    )
                    output(f"turn={turn} played={generated}")
                    recognition_failures += 1
                else:
                    output(f"turn={turn} reply=skipped reason={failure_reason}")
                completed_turns += 1
                continue

            recognition_failures = 0
            if is_repeat_reply_transcript(transcript):
                if realtime is not None:
                    realtime.discard_pending()
                if last_spoken_source is not None:
                    output(
                        f"turn={turn} repeated={last_spoken_source} "
                        "reason=repeat-request"
                    )
                    play_with_stop_interrupt(
                        last_spoken_source,
                        turn,
                        reason="repeat-request",
                    )
                    output(f"turn={turn} played={last_spoken_source}")
                else:
                    output(
                        f"turn={turn} reply={NOTHING_TO_REPEAT_REPLY} "
                        "reason=nothing-to-repeat"
                    )
                    generated = synthesize_reply(
                        NOTHING_TO_REPEAT_REPLY,
                        speech_output,
                    )
                    output(f"turn={turn} synthesized={generated}")
                    play_with_stop_interrupt(
                        generated,
                        turn,
                        reason="nothing-to-repeat",
                    )
                    output(f"turn={turn} played={generated}")
                completed_turns += 1
                continue

            if mobility_confirmation_pending:
                if is_mobility_cancel_transcript(transcript):
                    mobility_confirmation_pending = False
                    reply = MOBILITY_CANCEL_REPLY
                    reason = "mobility-start-cancelled"
                elif is_mobility_confirm_transcript(transcript):
                    mobility_confirmation_pending = False
                    reply = MOBILITY_UNAVAILABLE_REPLY
                    reason = "mobility-unavailable"
                    power_state = read_power_good(turn)
                    if power_good is not None and power_state is not True:
                        reply = (
                            POWER_LOW_REPLY
                            if power_state is False
                            else POWER_UNAVAILABLE_REPLY
                        )
                        reason = (
                            "power-low"
                            if power_state is False
                            else "power-unavailable"
                        )
                    elif start_mobility is not None:
                        try:
                            started = start_mobility()
                            reply = (
                                MOBILITY_START_REPLY
                                if started
                                else MOBILITY_ALREADY_RUNNING_REPLY
                            )
                            reason = (
                                "mobility-start" if started else "mobility-running"
                            )
                        except RuntimeError as exc:
                            output(f"turn={turn} mobility=error detail={exc}")
                else:
                    reply = MOBILITY_CONFIRM_AGAIN_REPLY
                    reason = "mobility-confirmation-required"
                output(f"turn={turn} reply={reply} reason={reason}")
                generated = synthesize_reply(reply, speech_output)
                output(f"turn={turn} synthesized={generated}")
                confirmation_reaction = (
                    ConversationReaction.CAUTIOUS
                    if reason in {"power-low", "power-unavailable"}
                    else ConversationReaction.CONFUSED
                    if reason == "mobility-confirmation-required"
                    else ConversationReaction.WARM
                )
                play_with_stop_interrupt(
                    generated,
                    turn,
                    confirmation_reaction,
                    reason,
                )
                output(f"turn={turn} played={generated}")
                completed_turns += 1
                continue

            if is_power_status_transcript(transcript) and power_good is not None:
                power_state = read_power_good(turn)
                reply = (
                    POWER_GOOD_REPLY
                    if power_state is True
                    else POWER_LOW_REPLY
                    if power_state is False
                    else POWER_UNAVAILABLE_REPLY
                )
                output(f"turn={turn} reply={reply} reason=power-status")
                generated = synthesize_reply(reply, speech_output)
                output(f"turn={turn} synthesized={generated}")
                power_reaction = (
                    ConversationReaction.CALM
                    if power_state is True
                    else ConversationReaction.CAUTIOUS
                )
                play_with_stop_interrupt(
                    generated,
                    turn,
                    power_reaction,
                    "power-status",
                )
                output(f"turn={turn} played={generated}")
                completed_turns += 1
                continue

            game_handles_end = (
                child_game_active is not None
                and child_game_active()
                and is_game_end_transcript(transcript)
            )
            if is_farewell_transcript(transcript) and not game_handles_end:
                was_moving = (
                    mobility_active is not None and mobility_active()
                )
                if stop_mobility is not None:
                    stop_mobility()
                goodbye = MOBILITY_FAREWELL_REPLY if was_moving else farewell_reply
                output(
                    f"turn={turn} reply={goodbye} "
                    "reason=conversation-ended"
                )
                generated = synthesize_reply(goodbye, speech_output)
                output(f"turn={turn} synthesized={generated}")
                play_with_stop_interrupt(generated, turn, reason="farewell")
                output(f"turn={turn} played={generated}")
                completed_turns += 1
                break

            if is_mobility_start_transcript(transcript):
                reply = MOBILITY_UNAVAILABLE_REPLY
                reason = "mobility-unavailable"
                power_state = read_power_good(turn)
                if power_good is not None and power_state is not True:
                    reply = (
                        POWER_LOW_REPLY
                        if power_state is False
                        else POWER_UNAVAILABLE_REPLY
                    )
                    reason = (
                        "power-low"
                        if power_state is False
                        else "power-unavailable"
                    )
                elif mobility_active is not None and mobility_active():
                    reply = MOBILITY_ALREADY_RUNNING_REPLY
                    reason = "mobility-running"
                elif start_mobility is not None:
                    mobility_confirmation_pending = True
                    reply = MOBILITY_CONFIRM_REPLY
                    reason = "mobility-confirmation-requested"
                output(f"turn={turn} reply={reply} reason={reason}")
                generated = synthesize_reply(reply, speech_output)
                output(f"turn={turn} synthesized={generated}")
                start_reaction = (
                    ConversationReaction.CAUTIOUS
                    if reason in {
                        "power-low",
                        "power-unavailable",
                        "mobility-unavailable",
                    }
                    else ConversationReaction.CURIOUS
                )
                play_with_stop_interrupt(generated, turn, start_reaction, reason)
                output(f"turn={turn} played={generated}")
                completed_turns += 1
                continue

            if is_ambiguous_mobility_transcript(transcript):
                output(
                    f"turn={turn} reply={MOBILITY_CLARIFY_REPLY} "
                    "reason=ambiguous-mobility-command"
                )
                generated = synthesize_reply(
                    MOBILITY_CLARIFY_REPLY,
                    speech_output,
                )
                output(f"turn={turn} synthesized={generated}")
                play_with_stop_interrupt(
                    generated,
                    turn,
                    ConversationReaction.CONFUSED,
                    "ambiguous-mobility-command",
                )
                output(f"turn={turn} played={generated}")
                completed_turns += 1
                continue

            if handle_profile_memory is not None:
                memory_reply = handle_profile_memory(transcript)
                if memory_reply is not None:
                    output(f"turn={turn} reply={memory_reply} reason=local-memory")
                    generated = synthesize_reply(memory_reply, speech_output)
                    output(f"turn={turn} synthesized={generated}")
                    play_with_stop_interrupt(
                        generated,
                        turn,
                        ConversationReaction.HAPPY,
                        "local-memory",
                    )
                    output(f"turn={turn} played={generated}")
                    completed_turns += 1
                    continue

            if handle_shared_experience is not None:
                experience_reply = handle_shared_experience(transcript)
                if experience_reply is not None:
                    output(
                        f"turn={turn} reply={experience_reply} "
                        "reason=shared-experience"
                    )
                    generated = synthesize_reply(experience_reply, speech_output)
                    output(f"turn={turn} synthesized={generated}")
                    play_with_stop_interrupt(
                        generated,
                        turn,
                        ConversationReaction.WARM,
                        "shared-experience",
                    )
                    output(f"turn={turn} played={generated}")
                    completed_turns += 1
                    continue

            if handle_child_game is not None:
                game_reply = handle_child_game(transcript)
                if game_reply is not None:
                    output(f"turn={turn} reply={game_reply} reason=child-game")
                    generated = synthesize_reply(game_reply, speech_output)
                    output(f"turn={turn} synthesized={generated}")
                    play_with_stop_interrupt(
                        generated,
                        turn,
                        ConversationReaction.HAPPY,
                        "child-game",
                    )
                    output(f"turn={turn} played={generated}")
                    completed_turns += 1
                    continue

            if handle_local_short_reply is not None:
                local_reply = handle_local_short_reply(transcript)
                if local_reply is not None:
                    reply = local_reply.text
                    if realtime is not None:
                        try:
                            realtime.record_local_reply(reply)
                        except RuntimeError as exc:
                            output(f"turn={turn} realtime=context-error detail={exc}")
                    output(
                        f"turn={turn} timing=reply seconds=0.000 local=true"
                    )
                    output(
                        f"turn={turn} reply={reply} reason=local-short-reply "
                        f"intent={local_reply.intent}"
                    )
                    reaction = (
                        ConversationReaction.HAPPY
                        if local_reply.intent in {"greeting", "success", "fun"}
                        else ConversationReaction.WARM
                    )
                    generated = stream_and_play_reply(
                        reply,
                        speech_output,
                        reaction,
                        "local-short-reply",
                    )
                    if generated is None:
                        generated = synthesize_reply(reply, speech_output)
                        output(f"turn={turn} synthesized={generated}")
                        play_with_stop_interrupt(
                            generated,
                            turn,
                            reaction,
                            "local-short-reply",
                        )
                    else:
                        output(
                            f"turn={turn} synthesized={generated} streaming=true"
                        )
                    output(f"turn={turn} played={generated}")
                    if on_exchange is not None and not reply_interrupted:
                        try:
                            on_exchange(transcript, reply)
                        except RuntimeError as exc:
                            output(f"turn={turn} memory=error detail={exc}")
                    completed_turns += 1
                    continue

            if realtime is not None and realtime_input_available:
                started = clock()
                emitted_audio = False
                chunks = iter(realtime.stream_reply(transcript, speech_output))
                try:
                    first_chunk = next(chunks)
                    play_pcm = getattr(player, "play_pcm16_stream", None)

                    def pcm_chunks():
                        try:
                            yield first_chunk
                            yield from chunks
                        finally:
                            chunks.close()

                    def first_audio_played() -> None:
                        nonlocal emitted_audio
                        emitted_audio = True
                        state.transition(
                            ConversationPhase.SPEAKING, ConversationReaction.WARM,
                            "realtime-reply",
                        )
                        output(f"turn={turn} timing=recording-to-playback seconds={clock() - recorded_at:.3f} realtime=true")

                    output(f"turn={turn} timing=realtime-first-audio seconds={clock() - started:.3f}")
                    if callable(play_pcm):
                        play_pcm(
                            pcm_chunks(), sample_rate=REALTIME_SAMPLE_RATE,
                            on_interrupt=realtime.cancel,
                            on_first_chunk=first_audio_played,
                        )
                    else:
                        for _ in pcm_chunks():
                            pass
                        emitted_audio = True
                        state.transition(
                            ConversationPhase.SPEAKING, ConversationReaction.WARM,
                            "realtime-reply",
                        )
                        output(f"turn={turn} timing=recording-to-playback seconds={clock() - recorded_at:.3f} realtime=true buffered=true")
                        player.play(speech_output)
                    last_spoken_source = speech_output
                    output(f"turn={turn} timing=realtime-playback-complete seconds={clock() - started:.3f}")
                    interrupted = bool(getattr(player, "last_interrupted", False))
                    if interrupted:
                        realtime.invalidate_last_reply()
                    output(
                        f"turn={turn} realtime=reply reply-chars={len(realtime.last_reply_text)} "
                        f"reply-mode={realtime.last_reply_mode} "
                        f"interrupted={str(interrupted).lower()}"
                    )
                    handle_playback_stop(turn)
                    if on_exchange is not None and realtime.last_completed and not interrupted:
                        try:
                            on_exchange(transcript, realtime.last_reply_text)
                        except RuntimeError as exc:
                            output(f"turn={turn} memory=error detail={exc}")
                    completed_turns += 1
                    continue
                except (RuntimeError, StopIteration) as exc:
                    chunks.close()
                    output(f"turn={turn} realtime=fallback stage=reply audio-started={str(emitted_audio).lower()} detail={exc}")
                    if emitted_audio:
                        # Never replay a second answer over a partial spoken answer.
                        realtime.invalidate_last_reply()
                        handle_playback_stop(turn)
                        completed_turns += 1
                        continue
                    realtime.close()

            started = clock()
            reply = reply_generator.reply(transcript)
            output(f"turn={turn} timing=reply seconds={clock() - started:.3f}")
            output(f"turn={turn} reply={reply}")
            generated = stream_and_play_reply(reply, speech_output)
            if generated is None:
                generated = synthesize_reply(reply, speech_output)
                output(f"turn={turn} synthesized={generated}")
                play_with_stop_interrupt(generated, turn)
            else:
                output(f"turn={turn} synthesized={generated} streaming=true")
            output(f"turn={turn} played={generated}")
            if realtime is not None and not reply_interrupted:
                realtime.record_fallback_reply(transcript, reply)
            if on_exchange is not None and not reply_interrupted:
                try:
                    on_exchange(transcript, reply)
                except RuntimeError as exc:
                    output(f"turn={turn} memory=error detail={exc}")
            completed_turns += 1
    except KeyboardInterrupt:
        if not catch_interrupt:
            raise
        output("Stopping conversation loop.")
    finally:
        try:
            if realtime is not None:
                realtime.close()
        finally:
            state.transition(
                ConversationPhase.STOPPED,
                ConversationReaction.CALM,
                "session-ended",
            )
    return completed_turns


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not 0 < args.semantic_silence_duration <= 60:
        parser.error("Semantic silence duration must be between 0 and 60 seconds.")
    if not 1 <= args.conversation_display_port <= 65535:
        parser.error("Conversation display port must be between 1 and 65535.")
    if args.conversation_backend == "realtime" and args.sample_rate != REALTIME_SAMPLE_RATE:
        parser.error("Realtime requires --sample-rate 24000.")
    realtime = (
        RealtimeConversation(
            model=args.realtime_model, timeout=args.realtime_timeout,
            turn_detection=args.realtime_turn_detection,
            semantic_eagerness=args.semantic_eagerness,
            empty_commit_grace=args.empty_commit_grace,
            voice=args.speech_voice, speed=args.speech_speed,
            child_mode=args.child_mode, speech_style=args.speech_style,
            transcription_model=args.transcription_model,
            transcription_prompt=args.transcription_prompt or (
                CHILD_TRANSCRIPTION_PROMPT if args.child_mode else None
            ),
            remember_context=args.memory != "none", memory_turns=args.memory_turns,
        )
        if args.conversation_backend == "realtime" else None
    )
    if args.audio_backend == "alsa-vad":
        recorder = AlsaVoiceActivatedRecorder(
            device=args.audio_device,
            threshold=args.speech_threshold,
            silence_duration=args.silence_duration,
            semantic_silence_duration=args.semantic_silence_duration,
            max_wait=args.max_wait,
            pre_roll=args.pre_roll,
        )
    else:
        recorder = create_recorder(args.audio_backend, args.audio_device)
    transcriber = create_transcriber(
        args.transcription_backend,
        model=args.transcription_model,
        mock_text=args.mock_text,
        prompt=(
            args.transcription_prompt
            or (CHILD_TRANSCRIPTION_PROMPT if args.child_mode else None)
        ),
    )
    reply_generator = create_reply_generator(
        args.reply_backend,
        model=args.reply_model,
        mock_reply=args.mock_reply,
        remember_context=args.memory != "none",
        max_context_turns=args.memory_turns,
        child_mode=args.child_mode,
        reasoning_effort=args.reply_reasoning_effort,
    )
    synthesizer = create_synthesizer(
        args.speech_backend,
        model=args.speech_model,
        voice=args.speech_voice,
        style=args.speech_style,
        speed=args.speech_speed,
        chunk_bytes=args.speech_chunk_bytes,
        fixed_cache_dir=args.fixed_speech_cache,
    )
    player = create_player(
        args.playback_backend,
        args.playback_device,
        capture_device=args.audio_device,
        interruption_threshold=args.barge_in_threshold,
        stop_word_model=(
            args.wake_word_model
            if args.mobility_backend != "off"
            and args.playback_backend == "alsa-interruptible"
            else None
        ),
    )
    turns = "until-Ctrl+C" if args.turns == 0 else str(args.turns)
    print(
        f"conversation-loop turns={turns} audio={args.audio_backend} "
        f"transcription={args.transcription_backend} reply={args.reply_backend} "
        f"child-mode={'on' if args.child_mode else 'off'} "
        f"memory={args.memory} speech={args.speech_backend} "
        f"speech-style={args.speech_style} speech-speed={args.speech_speed} "
        f"speech-chunk-bytes={args.speech_chunk_bytes} "
        f"fixed-speech-cache={'on' if args.fixed_speech_cache is not None else 'off'} "
        f"shared-experience-memory="
        f"{'on' if args.shared_experience_memory else 'off'} "
        f"local-short-replies={'on' if args.local_short_replies else 'off'} "
        f"playback={args.playback_backend} "
        f"start-trigger={args.start_trigger}"
        f" conversation-backend={args.conversation_backend} realtime-model={args.realtime_model}"
        f" realtime-turn-detection={args.realtime_turn_detection}"
        f" semantic-eagerness={args.semantic_eagerness}"
        f" empty-commit-grace={args.empty_commit_grace}"
    )
    if args.child_mode:
        print(
            "child-mode=supervised-test-only "
            "personal-data=do-not-share-without-required-data-controls"
        )
    conversation_store = (
        ConversationMemoryStore(args.conversation_memory_file, max_entries=None)
        if args.auto_conversation_memory or args.memory == "persistent"
        else None
    )
    active_session_id: str | None = None
    active_turn = 0
    if conversation_store is not None and args.memory == "persistent":
        def provide_conversation_history(query: str) -> list[dict[str, str]]:
            started = time.monotonic()
            try:
                return [
                    {
                        "日時": entry["timestamp"],
                        "user": entry["user"],
                        "Buddy": entry["assistant"],
                    }
                    for entry in conversation_store.relevant(
                        query,
                        limit=4,
                        exclude_session=active_session_id,
                    )
                ]
            except RuntimeError as exc:
                print(f"cross-session-memory=search-error detail={exc}")
                return []
            finally:
                print(f"turn={active_turn} timing=memory-search seconds={time.monotonic() - started:.3f}")

        for target in (reply_generator, realtime):
            set_history_provider = getattr(
                target, "set_conversation_history_provider", None
            )
            if callable(set_history_provider):
                set_history_provider(provide_conversation_history)
    power_monitor = (
        RaspberryPiPowerMonitor()
        if args.power_monitor == "raspberry-pi"
        else None
    )
    child_game = ChildGameController() if args.child_games else None
    local_short_replies = (
        LocalShortReplyController() if args.local_short_replies else None
    )
    profile_memory = SpokenProfileMemory(ParentManagedMemory(args.profile_memory))
    shared_experience = None
    if args.shared_experience_memory:
        shared_experience_store = SharedExperienceStore(
            args.shared_experience_memory_file
        )
        shared_experience = SpokenSharedExperienceMemory(shared_experience_store)
        set_shared_experience_provider = getattr(
            reply_generator,
            "set_shared_experience_provider",
            None,
        )
        if callable(set_shared_experience_provider):
            def provide_shared_experiences(query: str) -> list[str]:
                try:
                    return [
                        entry["summary"]
                        for entry in shared_experience_store.relevant(query)
                    ]
                except RuntimeError as exc:
                    print(f"shared-experience-memory=error detail={exc}")
                    return []

            set_shared_experience_provider(provide_shared_experiences)
            if realtime is not None:
                realtime.set_shared_experience_provider(provide_shared_experiences)
    current_activation = TriggerActivation.USER
    conversation_event_sink: Any | None = None
    display_transcript: Callable[[str | None], None] | None = None
    if args.conversation_events == "ros2":
        from buddy_ros.conversation_events import Ros2ConversationEventSink

        conversation_event_sink = Ros2ConversationEventSink()
    mobility = (
        PersonFollowProcessController(
            speed=args.mobility_speed,
            stop_distance=args.mobility_stop_distance,
            resume_distance=args.mobility_resume_distance,
            turn_pulse=args.mobility_turn_pulse,
            working_directory=Path.cwd(),
        )
        if args.mobility_backend == "person-follow"
        else Ros2FollowController()
        if args.mobility_backend == "ros2-follow"
        else None
    )
    orient_session: Callable[[], str] | None = None
    if args.orientation_backend != "off":
        from robot.conversation_orientation import orient_to_person
        from robot.motor import BuddyDrive, MockMotorDriver
        from robot.person_detection import MediaPipePersonDetector
        from robot.picamera2_driver import Picamera2FrameSource

        detector = MediaPipePersonDetector(
            model_path=args.person_model,
            helper_path=args.person_model_helper,
        )

        def orient_session() -> str:
            if args.orientation_backend == "gpiozero":
                from robot.gpiozero_driver import Tb6612GpioDriver

                driver = Tb6612GpioDriver()
            else:
                driver = MockMotorDriver()
            return orient_to_person(
                source=Picamera2FrameSource(width=640, height=480),
                detector=detector,
                drive=BuddyDrive(driver, max_speed=args.orientation_speed),
                attempts=args.orientation_attempts,
                speed=args.orientation_speed,
                pulse=args.orientation_pulse,
            )

    def run_session_inner(session_id: str, *, catch_interrupt: bool = True) -> int:
        current_turn = 0

        def session_output(line: str) -> None:
            nonlocal current_turn, active_turn
            match = re.match(r"^turn=(\d+) ", line)
            if match:
                current_turn = int(match[1])
                active_turn = current_turn
            print(line)

        remember_exchange: Callable[[str, str], None] | None = None
        if conversation_store is not None:
            def remember_exchange(user: str, assistant: str) -> None:
                started = time.monotonic()
                try:
                    conversation_store.append(
                        session=session_id,
                        user=user,
                        assistant=assistant,
                        turn=current_turn,
                    )
                finally:
                    print(f"turn={current_turn} timing=memory-append seconds={time.monotonic() - started:.3f}")

        if orient_session is not None:
            orient_session()
        return run_conversation_loop(
            recorder=recorder,
            transcriber=transcriber,
            reply_generator=reply_generator,
            synthesizer=synthesizer,
            player=player,
            input_path=args.input,
            speech_output=args.speech_output,
            duration=args.duration,
            sample_rate=args.sample_rate,
            language=args.language,
            turns=args.turns,
            pause=args.pause,
            retry_replies=(
                CHILD_RETRY_REPLIES if args.child_mode else DEFAULT_RETRY_REPLIES
            ),
            max_silence_turns=(
                1
                if current_activation is TriggerActivation.PROACTIVE
                else args.max_silence_turns
            ),
            on_exchange=remember_exchange,
            start_mobility=None if mobility is None else mobility.start,
            stop_mobility=None if mobility is None else mobility.stop,
            mobility_active=None if mobility is None else lambda: mobility.active,
            power_good=(
                None if power_monitor is None else power_monitor.is_power_good
            ),
            handle_child_game=(
                None if child_game is None else child_game.handle
            ),
            child_game_active=(
                None if child_game is None else lambda: child_game.active
            ),
            handle_profile_memory=profile_memory.handle,
            handle_shared_experience=(
                None if shared_experience is None else shared_experience.handle
            ),
            handle_local_short_reply=(
                None if local_short_replies is None else local_short_replies.reply
            ),
            on_conversation_event=conversation_event_sink,
            on_transcript=display_transcript,
            reject_transcript=(
                is_unreliable_child_transcript
                if args.child_mode
                else is_unreliable_transcript
            ),
            catch_interrupt=catch_interrupt,
            realtime=realtime,
            output=session_output,
        )

    def run_session(*, catch_interrupt: bool = True) -> int:
        nonlocal active_session_id
        session_id = uuid4().hex
        active_session_id = session_id
        print(f"session-start id={session_id} backend={args.conversation_backend} "
              f"turn-detection={args.realtime_turn_detection}")
        try:
            completed = run_session_inner(session_id, catch_interrupt=catch_interrupt)
        except KeyboardInterrupt:
            print(f"session-end id={session_id} status=interrupted")
            raise
        except Exception:
            print(f"session-end id={session_id} status=failed")
            raise
        print(f"session-end id={session_id} status=completed completed-turns={completed}")
        return completed

    if args.conversation_display:
        from robot.conversation_display import ConversationDisplay, ConversationEventSinks

        try:
            display = ConversationDisplay(
                args.conversation_display_host, args.conversation_display_port,
            )
        except OSError as exc:
            # A display failure must not stop conversation or existing ROS safety.
            print(f"conversation-display=unavailable detail={exc}")
        else:
            display_transcript = display.update_transcript
            sinks = (conversation_event_sink, display) if conversation_event_sink else (display,)
            conversation_event_sink = ConversationEventSinks(*sinks)
            print(f"conversation-display=ready host={args.conversation_display_host} "
                  f"port={args.conversation_display_port}")

    if args.start_trigger == "immediate":
        try:
            run_session()
        finally:
            if mobility is not None:
                mobility.close()
            if conversation_event_sink is not None:
                conversation_event_sink.close()
        return 0

    trigger = create_start_trigger(
        args.start_trigger,
        button_pin=args.button_pin,
        wake_word_device=args.wake_word_device or args.audio_device,
        wake_word_model=args.wake_word_model,
        wake_phrase=args.wake_phrase,
        proactive_interval=args.proactive_interval,
        proactive_allowed=lambda: is_active_hour(
            datetime.now().hour,
            args.proactive_start_hour,
            args.proactive_end_hour,
        ),
    )
    reset_context = getattr(reply_generator, "reset_context", None)
    wake_chime: Path | None = None
    if args.start_trigger == "wakeword":
        wake_chime = generate_engine_rev(
            Path("captures/audio/wake-engine.wav"),
            duration=0.38,
            volume=0.18,
        )

    def prepare_session() -> None:
        nonlocal current_activation
        current_activation = getattr(
            trigger,
            "activation",
            TriggerActivation.USER,
        )
        if callable(reset_context):
            reset_context()
        if realtime is not None:
            realtime.reset_context()
        if current_activation is TriggerActivation.PROACTIVE:
            if conversation_event_sink is not None:
                conversation_event_sink(
                    ConversationEvent(
                        ConversationPhase.THINKING,
                        ConversationReaction.CURIOUS,
                        "preparing-invitation",
                    )
                )
            try:
                invitation = synthesizer.synthesize(
                    PROACTIVE_INVITATION,
                    Path("captures/audio/proactive-invitation.wav"),
                )
                if conversation_event_sink is not None:
                    conversation_event_sink(ConversationEvent(
                        ConversationPhase.SPEAKING, ConversationReaction.WARM,
                        "proactive-invitation",
                    ))
                player.play(invitation)
            except RuntimeError as exc:
                print(f"proactive-invitation=error detail={exc}")
                if wake_chime is not None:
                    if conversation_event_sink is not None:
                        conversation_event_sink(ConversationEvent(
                            ConversationPhase.SPEAKING, ConversationReaction.CURIOUS,
                            "wake-chime-fallback",
                        ))
                    player.play(wake_chime)
        elif wake_chime is not None:
            if conversation_event_sink is not None:
                conversation_event_sink(
                    ConversationEvent(
                        ConversationPhase.SPEAKING,
                        ConversationReaction.CURIOUS,
                        "wake-word-recognized",
                    )
                )
            player.play(wake_chime)

    def publish_interaction_state(interaction_state: InteractionState) -> None:
        if conversation_event_sink is None:
            return
        phase = {
            InteractionState.WAITING: ConversationPhase.WAITING,
            InteractionState.CONVERSATION: ConversationPhase.THINKING,
            InteractionState.STOPPED: ConversationPhase.STOPPED,
        }[interaction_state]
        reaction = (
            ConversationReaction.CURIOUS
            if interaction_state is InteractionState.CONVERSATION
            else ConversationReaction.CALM
        )
        conversation_event_sink(
            ConversationEvent(
                phase,
                reaction,
                f"station-{interaction_state.value}",
            )
        )

    try:
        run_interaction_station(
            trigger=trigger,
            run_session=lambda: run_session(catch_interrupt=False),
            sessions=args.sessions,
            rearm_delay=(
                args.wake_word_rearm_delay
                if args.start_trigger == "wakeword"
                else 0.0
            ),
            reset_session=prepare_session,
            on_state_change=publish_interaction_state,
        )
    finally:
        if mobility is not None:
            mobility.close()
        if conversation_event_sink is not None:
            conversation_event_sink.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
