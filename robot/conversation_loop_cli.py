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
        "--playback-backend", choices=("mock", "alsa"), default="mock"
    )
    parser.add_argument("--playback-device", default="default")
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
    reject_transcript: Callable[[str], bool] | None = None,
    output: Callable[[str], None] = print,
    sleeper: Callable[[float], None] = time.sleep,
    catch_interrupt: bool = True,
) -> int:
    if turns < 0:
        raise ValueError("turns must be 0 or greater")

    completed_turns = 0
    recognition_failures = 0
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
    )
    synthesizer = create_synthesizer(
        args.speech_backend,
        model=args.speech_model,
        voice=args.speech_voice,
        style=args.speech_style,
    )
    player = create_player(args.playback_backend, args.playback_device)
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
    def run_session(*, catch_interrupt: bool = True) -> int:
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
