"""Prepare registered phrases without recording or playing audio."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import tempfile

from robot.fixed_speech import DEFAULT_FIXED_SPEECH_CACHE, FixedSpeechCache, fixed_speech_phrases
from robot.speech import (
    DEFAULT_SPEECH_MODEL, DEFAULT_SPEECH_VOICE, DEFAULT_SPEECH_STYLE,
    DEFAULT_SPEECH_SPEED, SPEECH_STYLES, get_speech_instructions,
)
from robot.speech_cli import create_synthesizer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("mock", "openai"), default="mock")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_FIXED_SPEECH_CACHE)
    parser.add_argument("--model", default=DEFAULT_SPEECH_MODEL)
    parser.add_argument("--voice", default=DEFAULT_SPEECH_VOICE)
    parser.add_argument("--style", choices=SPEECH_STYLES, default=DEFAULT_SPEECH_STYLE)
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEECH_SPEED)
    parser.add_argument("--list", action="store_true", help="List fixed phrases and settings without API calls or files.")
    parser.add_argument("--limit", type=int, default=None, help="Prepare only the first N registered phrases.")
    parser.add_argument("--force", action="store_true", help="Regenerate existing entries.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not 0.25 <= args.speed <= 4.0:
        parser.error("speed must be between 0.25 and 4.0")
    if args.limit is not None and args.limit <= 0:
        parser.error("limit must be positive")
    phrases = fixed_speech_phrases()[:args.limit]
    settings = dict(model=args.model, voice=args.voice,
                    instructions=get_speech_instructions(args.style), speed=args.speed)
    print(f"fixed-speech phrases={len(phrases)} backend={args.backend} model={args.model} "
          f"voice={args.voice} style={args.style} speed={args.speed}")
    if args.list:
        for number, text in enumerate(phrases, 1):
            print(f"{number}: {text}")
        return 0
    try:
        # The generator has no persistent reader; --force really regenerates.
        synthesizer = create_synthesizer(args.backend, model=args.model, voice=args.voice,
                                         style=args.style, speed=args.speed)
        cache = FixedSpeechCache(args.cache_dir)
        generated = reused = 0
        with tempfile.TemporaryDirectory(prefix="buddy-fixed-speech-") as directory:
            output = Path(directory) / "speech.wav"
            for text in phrases:
                if args.backend == "openai" and not args.force and cache.load(text, **settings) is not None:
                    reused += 1
                    continue
                synthesizer.synthesize(text, output)
                if args.backend == "mock":
                    preview = args.cache_dir.expanduser() / "mock-preview"
                    preview.mkdir(parents=True, exist_ok=True)
                    (preview / (hashlib.sha256(text.encode()).hexdigest() + ".wav")).write_bytes(output.read_bytes())
                else:
                    cache.save(text, output.read_bytes(), **settings)
                generated += 1
        print(f"fixed-speech generated={generated} reused={reused} "
              f"usable-cache={'true' if args.backend == 'openai' else 'false'}")
        return 0
    except (OSError, ValueError, RuntimeError):
        print("fixed-speech=failed: check backend configuration, audio format and output access")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
