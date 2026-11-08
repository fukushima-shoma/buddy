from __future__ import annotations

import argparse
from pathlib import Path

from robot.shared_experience_memory import (
    DEFAULT_SHARED_EXPERIENCE_PATH,
    SharedExperienceStore,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Buddy shared experiences.")
    parser.add_argument("--file", type=Path, default=DEFAULT_SHARED_EXPERIENCE_PATH)
    commands = parser.add_subparsers(dest="command", required=True)
    list_command = commands.add_parser("list")
    list_command.add_argument("--limit", type=int, default=20)
    add_command = commands.add_parser("add")
    add_command.add_argument("summary")
    delete_command = commands.add_parser("delete")
    delete_command.add_argument("experience_id")
    clear_command = commands.add_parser("clear")
    clear_command.add_argument("--yes", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    store = SharedExperienceStore(args.file)
    if args.command == "list":
        entries = store.recent(args.limit)
        if not entries:
            print("shared-experiences=empty")
        for entry in entries:
            print(
                f"id={entry['id']} time={entry['created_at']} "
                f"summary={entry['summary']}"
            )
        return 0
    if args.command == "add":
        entry = store.remember(args.summary)
        print(f"remembered={entry['id']} summary={entry['summary']}")
        return 0
    if args.command == "delete":
        deleted = store.delete(args.experience_id)
        print(f"deleted={str(deleted).lower()} id={args.experience_id}")
        return 0
    if not args.yes:
        raise RuntimeError("Add --yes to clear all shared experiences.")
    store.clear()
    print("shared-experiences=cleared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
