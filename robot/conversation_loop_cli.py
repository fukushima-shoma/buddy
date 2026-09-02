from __future__ import annotations

import argparse
from pathlib import Path
import time
from typing import Callable
from uuid import uuid4

from robot.audio import (
    AlsaVoiceActivatedRecorder,
    AudioPlayer,
    AudioRecorder,
    NoSpeechDetectedError,
    generate_tone,
)
from robot.audio_cli import create_player, create_recorder
from robot.child_games import ChildGameController, is_game_end_transcript
from robot.conversation import (
    DEFAULT_MEMORY_TURNS,
    DEFAULT_REPLY_MODEL,
    ReplyGenerator,
)
from robot.conversation_memory import (
    DEFAULT_CONVERSATION_MEMORY_PATH,
    ConversationMemoryStore,
)
from robot.conversation_intents import (
    DEFAULT_FAREWELL_REPLY,
    DEFAULT_INACTIVITY_REPLY,
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
    create_start_trigger,
    run_interaction_station,
)
from robot.mobility import PersonFollowProcessController, Ros2FollowController
from robot.profile_memory import DEFAULT_PROFILE_MEMORY_PATH, ParentManagedMemory
from robot.power import RaspberryPiPowerMonitor
from robot.reply_cli import create_reply_generator
from robot.speech import (
    DEFAULT_SPEECH_MODEL,
    DEFAULT_SPEECH_STYLE,
    DEFAULT_SPEECH_VOICE,
    SPEECH_STYLES,
    SpeechSynthesizer,
)
from robot.speech_cli import create_synthesizer
from robot.spoken_profile_memory import SpokenProfileMemory
from robot.transcribe_cli import create_transcriber
from robot.transcription import (
    CHILD_TRANSCRIPTION_PROMPT,
    DEFAULT_TRANSCRIPTION_MODEL,
    Transcriber,
    is_unreliable_child_transcript,
    is_unreliable_transcript,
)


CHILD_RETRY_REPLIES = (
    "ごめんね、よく聞こえなかったよ。もう一度、ゆっくり話してくれる？",
    "うまく聞き取れないみたい。近くの大人と一緒に、もう一度試してね。",
)
DEFAULT_RETRY_REPLIES = (
    "ごめんね、うまく聞き取れなかったよ。もう一度言ってくれる？",
    "あれ、聞き逃しちゃった。もう一回お願いしてもいい？",
    "ゆっくりで大丈夫だよ。もう一度聞かせてね。",
)
DEFAULT_MAX_SILENCE_TURNS = 2


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
    parser.add_argument("--reply-model", default=DEFAULT_REPLY_MODEL)
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
        "--memory",
        choices=("none", "session"),
        default="none",
        help="Use session memory backed by previous_response_id.",
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
        "--mobility-backend",
        choices=("off", "person-follow", "ros2-follow"),
        default="off",
        help="Allow exact spoken commands to start and stop person following.",
    )
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
    reject_transcript: Callable[[str], bool] | None = None,
    output: Callable[[str], None] = print,
    sleeper: Callable[[float], None] = time.sleep,
    catch_interrupt: bool = True,
) -> int:
    if turns < 0:
        raise ValueError("turns must be 0 or greater")
    if max_silence_turns < 0:
        raise ValueError("max silence turns must be 0 or greater")

    completed_turns = 0
    recognition_failures = 0
    consecutive_silences = 0
    mobility_confirmation_pending = False
    last_spoken_source: Path | None = None

    def play_with_stop_interrupt(source: Path, turn: int) -> None:
        nonlocal last_spoken_source
        last_spoken_source = source
        player.play(source)
        consume_stop = getattr(player, "consume_stop_request", None)
        if not callable(consume_stop) or not consume_stop():
            return
        stopped = stop_mobility() if stop_mobility is not None else False
        output(
            f"turn={turn} mobility={'stopped' if stopped else 'already-stopped'} "
            "reason=local-voice-interrupt"
        )
        confirmation = (
            MOBILITY_STOP_REPLY if stopped else MOBILITY_ALREADY_STOPPED_REPLY
        )
        generated = synthesizer.synthesize(confirmation, speech_output)
        output(f"turn={turn} interrupt-reply={confirmation}")
        output(f"turn={turn} interrupt-synthesized={generated}")
        player.play(generated)
        consume_stop()
        output(f"turn={turn} interrupt-played={generated}")

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
                    generated = synthesizer.synthesize(reply, speech_output)
                    output(f"turn={turn} synthesized={generated}")
                    play_with_stop_interrupt(generated, turn)
                    output(f"turn={turn} played={generated}")
                    completed_turns += 1
                    continue
            output(f"turn={turn} listening=true")
            try:
                source = recorder.record(
                    input_path,
                    duration=duration,
                    sample_rate=sample_rate,
                )
            except NoSpeechDetectedError:
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
                    generated = synthesizer.synthesize(
                        inactivity_reply,
                        speech_output,
                    )
                    output(f"turn={turn} synthesized={generated}")
                    play_with_stop_interrupt(generated, turn)
                    output(f"turn={turn} played={generated}")
                    completed_turns += 1
                    break
                if retry_replies:
                    retry = retry_replies[
                        min(recognition_failures, len(retry_replies) - 1)
                    ]
                    output(f"turn={turn} reply={retry} reason=no-speech")
                    generated = synthesizer.synthesize(retry, speech_output)
                    output(f"turn={turn} synthesized={generated}")
                    play_with_stop_interrupt(generated, turn)
                    output(f"turn={turn} played={generated}")
                    recognition_failures += 1
                completed_turns += 1
                continue
            output(f"turn={turn} recorded={source}")
            consecutive_silences = 0

            transcript = transcriber.transcribe(source, language=language)
            output(f"turn={turn} transcript={transcript or 'not-found'}")

            # A recognized stop command must bypass all rejection and dialog state.
            if transcript and is_mobility_stop_transcript(transcript):
                mobility_confirmation_pending = False
                stopped = stop_mobility() if stop_mobility is not None else False
                reply = (
                    MOBILITY_STOP_REPLY
                    if stopped
                    else MOBILITY_ALREADY_STOPPED_REPLY
                )
                reason = "mobility-stop" if stopped else "mobility-already-stopped"
                output(f"turn={turn} reply={reply} reason={reason}")
                generated = synthesizer.synthesize(reply, speech_output)
                output(f"turn={turn} synthesized={generated}")
                play_with_stop_interrupt(generated, turn)
                output(f"turn={turn} played={generated}")
                completed_turns += 1
                continue

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
                    generated = synthesizer.synthesize(retry, speech_output)
                    output(f"turn={turn} synthesized={generated}")
                    play_with_stop_interrupt(generated, turn)
                    output(f"turn={turn} played={generated}")
                    recognition_failures += 1
                else:
                    output(f"turn={turn} reply=skipped reason={failure_reason}")
                completed_turns += 1
                continue

            recognition_failures = 0
            if is_repeat_reply_transcript(transcript):
                if last_spoken_source is not None:
                    output(
                        f"turn={turn} repeated={last_spoken_source} "
                        "reason=repeat-request"
                    )
                    play_with_stop_interrupt(last_spoken_source, turn)
                    output(f"turn={turn} played={last_spoken_source}")
                else:
                    output(
                        f"turn={turn} reply={NOTHING_TO_REPEAT_REPLY} "
                        "reason=nothing-to-repeat"
                    )
                    generated = synthesizer.synthesize(
                        NOTHING_TO_REPEAT_REPLY,
                        speech_output,
                    )
                    output(f"turn={turn} synthesized={generated}")
                    play_with_stop_interrupt(generated, turn)
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
                generated = synthesizer.synthesize(reply, speech_output)
                output(f"turn={turn} synthesized={generated}")
                play_with_stop_interrupt(generated, turn)
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
                generated = synthesizer.synthesize(reply, speech_output)
                output(f"turn={turn} synthesized={generated}")
                play_with_stop_interrupt(generated, turn)
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
                generated = synthesizer.synthesize(goodbye, speech_output)
                output(f"turn={turn} synthesized={generated}")
                play_with_stop_interrupt(generated, turn)
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
                generated = synthesizer.synthesize(reply, speech_output)
                output(f"turn={turn} synthesized={generated}")
                play_with_stop_interrupt(generated, turn)
                output(f"turn={turn} played={generated}")
                completed_turns += 1
                continue

            if is_ambiguous_mobility_transcript(transcript):
                output(
                    f"turn={turn} reply={MOBILITY_CLARIFY_REPLY} "
                    "reason=ambiguous-mobility-command"
                )
                generated = synthesizer.synthesize(
                    MOBILITY_CLARIFY_REPLY,
                    speech_output,
                )
                output(f"turn={turn} synthesized={generated}")
                play_with_stop_interrupt(generated, turn)
                output(f"turn={turn} played={generated}")
                completed_turns += 1
                continue

            if handle_profile_memory is not None:
                memory_reply = handle_profile_memory(transcript)
                if memory_reply is not None:
                    output(f"turn={turn} reply={memory_reply} reason=local-memory")
                    generated = synthesizer.synthesize(memory_reply, speech_output)
                    output(f"turn={turn} synthesized={generated}")
                    play_with_stop_interrupt(generated, turn)
                    output(f"turn={turn} played={generated}")
                    completed_turns += 1
                    continue

            if handle_child_game is not None:
                game_reply = handle_child_game(transcript)
                if game_reply is not None:
                    output(f"turn={turn} reply={game_reply} reason=child-game")
                    generated = synthesizer.synthesize(game_reply, speech_output)
                    output(f"turn={turn} synthesized={generated}")
                    play_with_stop_interrupt(generated, turn)
                    output(f"turn={turn} played={generated}")
                    completed_turns += 1
                    continue

            reply = reply_generator.reply(transcript)
            output(f"turn={turn} reply={reply}")
            generated = synthesizer.synthesize(reply, speech_output)
            output(f"turn={turn} synthesized={generated}")
            play_with_stop_interrupt(generated, turn)
            output(f"turn={turn} played={generated}")
            if on_exchange is not None:
                try:
                    on_exchange(transcript, reply)
                except RuntimeError as exc:
                    output(f"turn={turn} memory=error detail={exc}")
            completed_turns += 1
    except KeyboardInterrupt:
        if not catch_interrupt:
            raise
        output("Stopping conversation loop.")
    return completed_turns


def main() -> int:
    args = build_parser().parse_args()
    if args.audio_backend == "alsa-vad":
        recorder = AlsaVoiceActivatedRecorder(
            device=args.audio_device,
            threshold=args.speech_threshold,
            silence_duration=args.silence_duration,
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
        remember_context=args.memory == "session",
        max_context_turns=args.memory_turns,
        child_mode=args.child_mode,
    )
    synthesizer = create_synthesizer(
        args.speech_backend,
        model=args.speech_model,
        voice=args.speech_voice,
        style=args.speech_style,
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
        f"speech-style={args.speech_style} playback={args.playback_backend} "
        f"start-trigger={args.start_trigger}"
    )
    if args.child_mode:
        print(
            "child-mode=supervised-test-only "
            "personal-data=do-not-share-without-required-data-controls"
        )
    conversation_store = (
        ConversationMemoryStore(args.conversation_memory_file)
        if args.auto_conversation_memory
        else None
    )
    power_monitor = (
        RaspberryPiPowerMonitor()
        if args.power_monitor == "raspberry-pi"
        else None
    )
    child_game = ChildGameController() if args.child_games else None
    profile_memory = SpokenProfileMemory(ParentManagedMemory(args.profile_memory))
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

    def run_session(*, catch_interrupt: bool = True) -> int:
        session_id = uuid4().hex
        remember_exchange: Callable[[str, str], None] | None = None
        if conversation_store is not None:
            def remember_exchange(user: str, assistant: str) -> None:
                conversation_store.append(
                    session=session_id,
                    user=user,
                    assistant=assistant,
                )

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
            max_silence_turns=args.max_silence_turns,
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
            reject_transcript=(
                is_unreliable_child_transcript
                if args.child_mode
                else is_unreliable_transcript
            ),
            catch_interrupt=catch_interrupt,
        )

    if args.start_trigger == "immediate":
        try:
            run_session()
        finally:
            if mobility is not None:
                mobility.close()
        return 0

    trigger = create_start_trigger(
        args.start_trigger,
        button_pin=args.button_pin,
        wake_word_device=args.wake_word_device or args.audio_device,
        wake_word_model=args.wake_word_model,
        wake_phrase=args.wake_phrase,
    )
    reset_context = getattr(reply_generator, "reset_context", None)
    wake_chime: Path | None = None
    if args.start_trigger == "wakeword":
        wake_chime = generate_tone(
            Path("captures/audio/wake-chime.wav"),
            frequency=880,
            duration=0.12,
            volume=0.15,
        )

    def prepare_session() -> None:
        if callable(reset_context):
            reset_context()
        if wake_chime is not None:
            player.play(wake_chime)

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
        )
    finally:
        if mobility is not None:
            mobility.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
