from __future__ import annotations

import argparse
from pathlib import Path

from robot.audio import AlsaAudioRecorder, MockAudioRecorder
from robot.conversation import DEFAULT_REPLY_MODEL
from robot.reply_cli import create_reply_generator
from robot.transcription import (
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
    parser.add_argument("--mock-text", default="こんにちは、Buddy")
    parser.add_argument(
        "--reply-backend",
        choices=("none", "mock", "openai"),
        default="none",
        help="Optionally generate one reply after transcription.",
    )
    parser.add_argument("--reply-model", default=DEFAULT_REPLY_MODEL)
    parser.add_argument("--mock-reply", default="こんにちは！今日は何をして遊ぶ？")


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
) -> Transcriber:
    if backend == "mock":
        return MockTranscriber(mock_text)
    return OpenAITranscriber(model=model)


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
        )
        print(f"reply={generator.reply(transcript)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
