from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Callable


DEFAULT_WAKE_PHRASE = "ねえ バディ"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train a Porcupine wake word model for Buddy."
    )
    parser.add_argument("--phrase", default=DEFAULT_WAKE_PHRASE)
    parser.add_argument("--language", default="ja")
    parser.add_argument("--platform", default="raspberry-pi")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("models/wakeword/nee-buddy_ja_raspberry-pi.ppn"),
    )
    return parser


def train_wake_word(
    *,
    phrase: str,
    language: str,
    platform: str,
    output: Path,
    access_key: str | None = None,
    trainer: Callable[..., Any] | None = None,
) -> Path:
    access_key = access_key or os.environ.get("PICOVOICE_ACCESS_KEY")
    if not access_key:
        raise RuntimeError(
            "PICOVOICE_ACCESS_KEY is not set. Export it before training."
        )
    if not phrase.strip():
        raise ValueError("wake word phrase must not be empty")
    if trainer is None:
        try:
            import pvporcupine
        except ImportError as exc:
            raise RuntimeError(
                "pvporcupine is required. Activate .venv and run: "
                "python -m pip install -r requirements-phase3.txt"
            ) from exc
        trainer = pvporcupine.train_wake_word_from_phrase

    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    trainer(access_key, str(output), language, phrase.strip(), platform)
    return output


def main() -> int:
    args = build_parser().parse_args()
    output = train_wake_word(
        phrase=args.phrase,
        language=args.language,
        platform=args.platform,
        output=args.output,
    )
    print(
        f"trained={output} phrase={args.phrase} language={args.language} "
        f"platform={args.platform}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
