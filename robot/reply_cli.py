from __future__ import annotations

import argparse

from robot.conversation import (
    DEFAULT_REPLY_MODEL,
    MockReplyGenerator,
    OpenAIReplyGenerator,
    ReplyGenerator,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate one Buddy reply.")
    parser.add_argument("text")
    parser.add_argument("--backend", choices=("mock", "openai"), default="mock")
    parser.add_argument("--model", default=DEFAULT_REPLY_MODEL)
    parser.add_argument("--mock-reply", default="こんにちは！今日は何をして遊ぶ？")
    return parser


def create_reply_generator(
    backend: str,
    *,
    model: str,
    mock_reply: str,
    remember_context: bool = False,
    max_context_turns: int = 6,
) -> ReplyGenerator:
    if backend == "mock":
        return MockReplyGenerator(mock_reply)
    return OpenAIReplyGenerator(
        model=model,
        remember_context=remember_context,
        max_context_turns=max_context_turns,
    )


def main() -> int:
    args = build_parser().parse_args()
    generator = create_reply_generator(
        args.backend,
        model=args.model,
        mock_reply=args.mock_reply,
    )
    print(f"reply={generator.reply(args.text)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
