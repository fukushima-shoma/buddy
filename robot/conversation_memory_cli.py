from __future__ import annotations

import argparse
from pathlib import Path

from robot.conversation_memory import (
    DEFAULT_CONVERSATION_MEMORY_PATH,
    ConversationMemoryStore,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect or clear Buddy conversation memory.")
    parser.add_argument("--file", type=Path, default=DEFAULT_CONVERSATION_MEMORY_PATH)
    commands = parser.add_subparsers(dest="command", required=True)
    list_command = commands.add_parser("list")
    list_command.add_argument("--limit", type=int, default=20)
    clear_command = commands.add_parser("clear")
    clear_command.add_argument("--yes", action="store_true")
    delete_command = commands.add_parser("delete-session")
    delete_command.add_argument("session")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    store = ConversationMemoryStore(args.file)
    if args.command == "list":
        entries = store.recent(args.limit)
        if not entries:
            print("conversation-memory=empty")
        for index, entry in enumerate(entries, 1):
            print(
                f"{index}. session={entry['session']} time={entry['timestamp']} "
                f"user={entry['user']} "
                f"buddy={entry['assistant']}"
            )
        return 0
    if args.command == "delete-session":
        removed = store.delete_session(args.session)
        print(f"deleted-session={args.session} entries={removed}")
        return 0
    if not args.yes:
        raise RuntimeError("Add --yes to clear all conversation memory.")
    store.clear()
    print("conversation-memory=cleared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
