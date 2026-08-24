from __future__ import annotations

import argparse
from typing import Mapping

from robot.conversation import (
    DEFAULT_MEMORY_TURNS,
    DEFAULT_REPLY_MODEL,
    MockReplyGenerator,
    OpenAIReplyGenerator,
    ReplyGenerator,
    get_reply_instructions,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate one Buddy reply.")
    parser.add_argument("text")
    parser.add_argument("--backend", choices=("mock", "openai"), default="mock")
    parser.add_argument("--model", default=DEFAULT_REPLY_MODEL)
    parser.add_argument("--mock-reply", default="こんにちは！今日は何をして遊ぶ？")
    parser.add_argument(
        "--child-mode",
        action="store_true",
        help="Use short, supervised, age-appropriate replies for a young child.",
    )
    return parser


def create_reply_generator(
    backend: str,
    *,
    model: str,
    mock_reply: str,
    remember_context: bool = False,
    max_context_turns: int = DEFAULT_MEMORY_TURNS,
    child_mode: bool = False,
    profile_facts: Mapping[str, str] | None = None,
) -> ReplyGenerator:
    if backend == "mock":
        return MockReplyGenerator(mock_reply)
    return OpenAIReplyGenerator(
        model=model,
        instructions=get_reply_instructions(child_mode, profile_facts),
        remember_context=remember_context,
        max_context_turns=max_context_turns,
    )


def main() -> int:
    args = build_parser().parse_args()
    generator = create_reply_generator(
        args.backend,
        model=args.model,
        mock_reply=args.mock_reply,
        child_mode=args.child_mode,
    )
    print(f"reply={generator.reply(args.text)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
