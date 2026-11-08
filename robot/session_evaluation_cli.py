"""Review the latest Buddy session locally, without opening hardware."""
from __future__ import annotations

import argparse
from pathlib import Path
import json
import subprocess
import sys
import time

from robot.conversation_memory import DEFAULT_CONVERSATION_MEMORY_PATH, ConversationMemoryStore
from robot.session_evaluation import evaluate_session, parse_sessions, render_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--log-file", type=Path)
    source.add_argument("--stdin", action="store_true")
    parser.add_argument("--memory-file", type=Path, default=DEFAULT_CONVERSATION_MEMORY_PATH)
    parser.add_argument("--session", default="latest")
    parser.add_argument("--completed", action="store_true", help="Only select completed sessions.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--review-context", action="store_true", help="Include private transcript and review rubric as JSON; no external API call.")
    parser.add_argument("--output", type=Path, help="Save the report locally.")
    args = parser.parse_args(argv)
    try:
        if args.stdin:
            sessions = parse_sessions(sys.stdin)
        elif args.log_file:
            with args.log_file.open() as lines:
                sessions = parse_sessions(lines)
        else:
            result = subprocess.run(
                ["journalctl", "-u", "buddy-conversation.service", "--since", "24 hours ago",
                 "-n", "20000", "-o", "json", "--no-pager"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode:
                raise RuntimeError("journal-unavailable: use --log-file or --stdin")
            sessions = parse_sessions(result.stdout.splitlines())
        snapshot_us = int(time.time() * 1_000_000)
        if args.completed:
            sessions = [session for session in sessions if session.status == "completed"]
        matches = sessions if args.session == "latest" else [session for session in sessions if session.id == args.session]
        if not matches:
            print("session-evaluation=no-matching-session", file=sys.stderr)
            return 1
        store = ConversationMemoryStore(args.memory_file)
        report = evaluate_session(matches[-1], store.load(), snapshot_us=snapshot_us,
                                  include_dialogue=args.review_context)
        rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n" if args.format == "json" or args.review_context else render_report(report)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            args.output.chmod(0o600)
        else:
            print(rendered, end="")
        return 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        print("session-evaluation=unavailable: check journal/file access and memory format", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
