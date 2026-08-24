from __future__ import annotations

import argparse
from pathlib import Path

from robot.audio_cli import create_player
from robot.speech import (
    DEFAULT_SPEECH_MODEL,
    DEFAULT_SPEECH_STYLE,
    DEFAULT_SPEECH_VOICE,
    MockSpeechSynthesizer,
    OpenAISpeechSynthesizer,
    SPEECH_STYLES,
    SpeechSynthesizer,
    get_speech_instructions,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate one Buddy speech WAV.")
    parser.add_argument("text")
    parser.add_argument("--backend", choices=("mock", "openai"), default="mock")
    parser.add_argument("--model", default=DEFAULT_SPEECH_MODEL)
    parser.add_argument("--voice", default=DEFAULT_SPEECH_VOICE)
    parser.add_argument("--style", choices=SPEECH_STYLES, default=DEFAULT_SPEECH_STYLE)
    parser.add_argument(
        "--output", type=Path, default=Path("captures/audio/reply.wav")
    )
    parser.add_argument(
        "--playback-backend", choices=("none", "mock", "alsa"), default="none"
    )
    parser.add_argument("--device", default="default")
    return parser


def create_synthesizer(
    backend: str,
    *,
    model: str,
    voice: str,
    style: str = DEFAULT_SPEECH_STYLE,
) -> SpeechSynthesizer:
    if backend == "mock":
        return MockSpeechSynthesizer()
    return OpenAISpeechSynthesizer(
        model=model,
        voice=voice,
        instructions=get_speech_instructions(style),
    )


def main() -> int:
    args = build_parser().parse_args()
    output = create_synthesizer(
        args.backend,
        model=args.model,
        voice=args.voice,
        style=args.style,
    ).synthesize(args.text, args.output)
    print(
        f"synthesized={output} backend={args.backend} "
        f"voice={args.voice} style={args.style}"
    )
    if args.playback_backend != "none":
        create_player(args.playback_backend, args.device).play(output)
        print(f"played={output} backend={args.playback_backend}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
