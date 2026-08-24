from __future__ import annotations

import argparse
from pathlib import Path

from robot.audio import AlsaAudioRecorder, MockAudioRecorder
from robot.audio_cli import create_player
from robot.conversation import DEFAULT_REPLY_MODEL
from robot.reply_cli import create_reply_generator
from robot.speech import (
    DEFAULT_SPEECH_MODEL,
    DEFAULT_SPEECH_STYLE,
    DEFAULT_SPEECH_VOICE,
    SPEECH_STYLES,
)
from robot.speech_cli import create_synthesizer
from robot.transcription import (
    CHILD_TRANSCRIPTION_PROMPT,
    DEFAULT_TRANSCRIPTION_MODEL,
    MockTranscriber,
    OpenAITranscriber,
    Transcriber,
)


def add_transcription_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--backend",
        choices=("mock", "openai"),
        default="mock",
        help="OpenAI is only called when explicitly selected.",
    )
    parser.add_argument("--model", default=DEFAULT_TRANSCRIPTION_MODEL)
    parser.add_argument("--language", default="ja")
    parser.add_argument(
        "--transcription-prompt",
        help="Optional context hint passed to the transcription model.",
    )
    parser.add_argument("--mock-text", default="こんにちは、Buddy")
    parser.add_argument(
        "--reply-backend",
        choices=("none", "mock", "openai"),
        default="none",
        help="Optionally generate one reply after transcription.",
    )
    parser.add_argument("--reply-model", default=DEFAULT_REPLY_MODEL)
    parser.add_argument("--mock-reply", default="こんにちは！今日は何をして遊ぶ？")
    parser.add_argument(
        "--child-mode",
        action="store_true",
        help="Use supervised replies suitable for a young child.",
    )
    parser.add_argument(
        "--speech-backend",
        choices=("none", "mock", "openai"),
        default="none",
        help="Optionally synthesize the generated reply as a WAV file.",
    )
    parser.add_argument("--speech-model", default=DEFAULT_SPEECH_MODEL)
    parser.add_argument("--speech-voice", default=DEFAULT_SPEECH_VOICE)
    parser.add_argument(
        "--speech-style", choices=SPEECH_STYLES, default=DEFAULT_SPEECH_STYLE
    )
    parser.add_argument(
        "--speech-output",
        type=Path,
        default=Path("captures/audio/reply.wav"),
    )
    parser.add_argument(
        "--playback-backend",
        choices=("none", "mock", "alsa"),
        default="none",
    )
    parser.add_argument("--playback-device", default="default")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Transcribe speech for Buddy.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    file_parser = subparsers.add_parser("file", help="Transcribe an audio file.")
    file_parser.add_argument("source", type=Path)
    add_transcription_arguments(file_parser)

    record_parser = subparsers.add_parser(
        "record", help="Record audio, then transcribe it."
    )
    record_parser.add_argument(
        "--audio-backend", choices=("mock", "alsa"), default="mock"
    )
    record_parser.add_argument("--device", default="default")
    record_parser.add_argument(
        "--output",
        type=Path,
        default=Path("captures/audio/transcription-input.wav"),
    )
    record_parser.add_argument("--duration", type=float, default=5.0)
    record_parser.add_argument("--sample-rate", type=int, default=16000)
    add_transcription_arguments(record_parser)
    return parser


def create_transcriber(
    backend: str,
    *,
    model: str,
    mock_text: str,
    prompt: str | None = None,
) -> Transcriber:
    if backend == "mock":
        return MockTranscriber(mock_text)
    return OpenAITranscriber(model=model, prompt=prompt)


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "file":
        source = args.source
    elif args.command == "record":
        recorder = (
            MockAudioRecorder()
            if args.audio_backend == "mock"
            else AlsaAudioRecorder(device=args.device)
        )
        source = recorder.record(
            args.output,
            duration=args.duration,
            sample_rate=args.sample_rate,
        )
        print(f"recorded={source} backend={args.audio_backend}")
    else:
        raise ValueError(f"Unsupported command: {args.command}")

    transcriber = create_transcriber(
        args.backend,
        model=args.model,
        mock_text=args.mock_text,
        prompt=(
            args.transcription_prompt
            or (CHILD_TRANSCRIPTION_PROMPT if args.child_mode else None)
        ),
    )
    transcript = transcriber.transcribe(source, language=args.language)
    print(f"transcript={transcript or 'not-found'}")
    if args.reply_backend != "none":
        if not transcript:
            print("reply=skipped reason=empty-transcript")
            return 0
        generator = create_reply_generator(
            args.reply_backend,
            model=args.reply_model,
            mock_reply=args.mock_reply,
            child_mode=args.child_mode,
        )
        reply = generator.reply(transcript)
        print(f"reply={reply}")
        if args.speech_backend != "none":
            synthesizer = create_synthesizer(
                args.speech_backend,
                model=args.speech_model,
                voice=args.speech_voice,
                style=args.speech_style,
            )
            speech_output = synthesizer.synthesize(reply, args.speech_output)
            print(
                f"synthesized={speech_output} backend={args.speech_backend} "
                f"voice={args.speech_voice} style={args.speech_style}"
            )
            if args.playback_backend != "none":
                create_player(args.playback_backend, args.playback_device).play(
                    speech_output
                )
                print(
                    f"played={speech_output} backend={args.playback_backend}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
