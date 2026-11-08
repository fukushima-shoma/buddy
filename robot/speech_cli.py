from __future__ import annotations

import argparse
from pathlib import Path

from robot.audio_cli import create_player
from robot.speech import (
    DEFAULT_SPEECH_MODEL,
    DEFAULT_SPEECH_SPEED,
    DEFAULT_SPEECH_STYLE,
    DEFAULT_SPEECH_VOICE,
    DEFAULT_SPEECH_CHUNK_BYTES,
    SPEECH_CHUNK_SIZES,
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
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEECH_SPEED)
    parser.add_argument("--chunk-bytes", type=int, choices=SPEECH_CHUNK_SIZES,
                        default=DEFAULT_SPEECH_CHUNK_BYTES)
    parser.add_argument("--fixed-speech-cache", type=Path, default=None,
                        help="Read prepared fixed phrases from this directory (disabled by default).")
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
    speed: float = DEFAULT_SPEECH_SPEED,
    chunk_bytes: int = DEFAULT_SPEECH_CHUNK_BYTES,
    fixed_cache_dir: Path | None = None,
) -> SpeechSynthesizer:
    if type(chunk_bytes) is not int or chunk_bytes not in SPEECH_CHUNK_SIZES:
        raise ValueError("Speech chunk bytes must be 2048, 4096, or 16384.")
    if backend == "mock":
        return MockSpeechSynthesizer()
    return OpenAISpeechSynthesizer(
        model=model,
        voice=voice,
        instructions=get_speech_instructions(style),
        speed=speed,
        chunk_bytes=chunk_bytes,
        fixed_cache_dir=fixed_cache_dir,
    )


def main() -> int:
    args = build_parser().parse_args()
    synthesizer = create_synthesizer(
        args.backend,
        model=args.model,
        voice=args.voice,
        style=args.style,
        speed=args.speed,
        chunk_bytes=args.chunk_bytes,
        fixed_cache_dir=args.fixed_speech_cache,
    )
    stream = getattr(synthesizer, "stream", None)
    if callable(stream):
        for _ in stream(args.text, args.output):
            pass
        output = args.output.expanduser()
    else:
        output = synthesizer.synthesize(args.text, args.output)
    print(
        f"synthesized={output} backend={args.backend} "
        f"voice={args.voice} style={args.style} speed={args.speed} "
        f"chunk-bytes={args.chunk_bytes} cache-source={getattr(synthesizer, 'last_cache_source', 'none')}"
    )
    if args.playback_backend != "none":
        create_player(args.playback_backend, args.device).play(output)
        print(f"played={output} backend={args.playback_backend}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
