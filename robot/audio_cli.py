from __future__ import annotations

import argparse
from pathlib import Path

from robot.audio import (
    AlsaAudioPlayer,
    AlsaAudioRecorder,
    AudioPlayer,
    AudioRecorder,
    MockAudioPlayer,
    MockAudioRecorder,
    generate_tone,
    inspect_wav,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Test Buddy's audio input and output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    tone = subparsers.add_parser("tone", help="Generate a speaker test WAV file.")
    tone.add_argument("--output", type=Path, default=Path("captures/audio/tone.wav"))
    tone.add_argument("--frequency", type=float, default=440.0)
    tone.add_argument("--duration", type=float, default=1.0)
    tone.add_argument("--sample-rate", type=int, default=16000)
    tone.add_argument("--volume", type=float, default=0.2)

    inspect = subparsers.add_parser("inspect", help="Show WAV file properties.")
    inspect.add_argument("source", type=Path)

    record = subparsers.add_parser("record", help="Record a mono WAV file.")
    record.add_argument("--backend", choices=("mock", "alsa"), default="mock")
    record.add_argument("--device", default="default")
    record.add_argument(
        "--output", type=Path, default=Path("captures/audio/recording.wav")
    )
    record.add_argument("--duration", type=float, default=3.0)
    record.add_argument("--sample-rate", type=int, default=16000)

    play = subparsers.add_parser("play", help="Play a WAV file.")
    play.add_argument("source", type=Path)
    play.add_argument("--backend", choices=("mock", "alsa"), default="mock")
    play.add_argument("--device", default="default")
    return parser


def create_recorder(backend: str, device: str) -> AudioRecorder:
    if backend == "mock":
        return MockAudioRecorder()
    return AlsaAudioRecorder(device=device)


def create_player(backend: str, device: str) -> AudioPlayer:
    if backend == "mock":
        return MockAudioPlayer()
    return AlsaAudioPlayer(device=device)


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "tone":
        output = generate_tone(
            args.output,
            frequency=args.frequency,
            duration=args.duration,
            sample_rate=args.sample_rate,
            volume=args.volume,
        )
        print(f"generated={output}")
        return 0
    if args.command == "inspect":
        info = inspect_wav(args.source)
        print(
            f"channels={info.channels} sample-width={info.sample_width} "
            f"sample-rate={info.sample_rate} frames={info.frames} "
            f"duration={info.duration:.2f}s"
        )
        return 0
    if args.command == "record":
        output = create_recorder(args.backend, args.device).record(
            args.output,
            duration=args.duration,
            sample_rate=args.sample_rate,
        )
        print(f"recorded={output} backend={args.backend}")
        return 0
    if args.command == "play":
        create_player(args.backend, args.device).play(args.source)
        print(f"played={args.source.expanduser()} backend={args.backend}")
        return 0
    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
