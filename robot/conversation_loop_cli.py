from __future__ import annotations

import argparse
from pathlib import Path
import time
from typing import Callable
import unicodedata

from robot.audio import (
    AlsaVoiceActivatedRecorder,
    AudioPlayer,
    AudioRecorder,
    NoSpeechDetectedError,
    generate_tone,
)
from robot.audio_cli import create_player, create_recorder
from robot.conversation import (
    DEFAULT_MEMORY_TURNS,
    DEFAULT_REPLY_MODEL,
    ReplyGenerator,
)
from robot.interaction import (
    DEFAULT_CONVERSATION_BUTTON_PIN,
    DEFAULT_WAKE_PHRASE,
    create_start_trigger,
    run_interaction_station,
)
from robot.profile_memory import DEFAULT_PROFILE_MEMORY_PATH, ParentManagedMemory
from robot.reply_cli import create_reply_generator
from robot.speech import (
    DEFAULT_SPEECH_MODEL,
    DEFAULT_SPEECH_STYLE,
    DEFAULT_SPEECH_VOICE,
    SPEECH_STYLES,
    SpeechSynthesizer,
)
from robot.speech_cli import create_synthesizer
from robot.transcribe_cli import create_transcriber
from robot.transcription import (
    CHILD_TRANSCRIPTION_PROMPT,
    DEFAULT_TRANSCRIPTION_MODEL,
    Transcriber,
    is_unreliable_child_transcript,
)


CHILD_RETRY_REPLIES = (
    "ごめんね、よく聞こえなかったよ。もう一度、ゆっくり話してくれる？",
    "うまく聞き取れないみたい。近くの大人と一緒に、もう一度試してね。",
)
FAREWELL_PHRASES = frozenset(
    {
        "バイバイ",
        "ばいばい",
        "じゃあバイバイ",
        "バイバイまたね",
        "またね",
        "さようなら",
        "さよなら",
        "おしまい",
        "お話おしまい",
    }
)
DEFAULT_FAREWELL_REPLY = "バイバイ。またお話ししようね。"
DEFAULT_MAX_SILENCE_TURNS = 2
DEFAULT_INACTIVITY_REPLY = "お話はおしまいかな。またお話ししようね。"


def is_farewell_transcript(transcript: str) -> bool:
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKC", transcript).casefold()
        if character.isalnum()
    )
    return normalized in FAREWELL_PHRASES


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
    try:
        while turns == 0 or completed_turns < turns:
            if completed_turns > 0 and pause > 0:
                sleeper(pause)
            turn = completed_turns + 1
            output(f"turn={turn} listening=true")
            try:
                source = recorder.record(
                    input_path,
                    duration=duration,
                    sample_rate=sample_rate,
                )
            except NoSpeechDetectedError:
                output(f"turn={turn} transcript=not-found reason=no-speech")
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
                    player.play(generated)
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
                    player.play(generated)
                    output(f"turn={turn} played={generated}")
                    recognition_failures += 1
                completed_turns += 1
                continue
            output(f"turn={turn} recorded={source}")
            consecutive_silences = 0

            transcript = transcriber.transcribe(source, language=language)
            output(f"turn={turn} transcript={transcript or 'not-found'}")
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
                    player.play(generated)
                    output(f"turn={turn} played={generated}")
                    recognition_failures += 1
                else:
                    output(f"turn={turn} reply=skipped reason={failure_reason}")
                completed_turns += 1
                continue

            recognition_failures = 0
            if is_farewell_transcript(transcript):
                output(
                    f"turn={turn} reply={farewell_reply} "
                    "reason=conversation-ended"
                )
                generated = synthesizer.synthesize(farewell_reply, speech_output)
                output(f"turn={turn} synthesized={generated}")
                player.play(generated)
                output(f"turn={turn} played={generated}")
                completed_turns += 1
                break

            reply = reply_generator.reply(transcript)
            output(f"turn={turn} reply={reply}")
            generated = synthesizer.synthesize(reply, speech_output)
            output(f"turn={turn} synthesized={generated}")
            player.play(generated)
            output(f"turn={turn} played={generated}")
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
        profile_facts=ParentManagedMemory(args.profile_memory).load(),
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
            retry_replies=CHILD_RETRY_REPLIES if args.child_mode else (),
            max_silence_turns=args.max_silence_turns,
            reject_transcript=(
                is_unreliable_child_transcript if args.child_mode else None
            ),
            catch_interrupt=catch_interrupt,
        )

    if args.start_trigger == "immediate":
        run_session()
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

    run_interaction_station(
        trigger=trigger,
        run_session=lambda: run_session(catch_interrupt=False),
        sessions=args.sessions,
        reset_session=prepare_session,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
