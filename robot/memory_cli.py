from __future__ import annotations

import argparse
from pathlib import Path

from robot.profile_memory import DEFAULT_PROFILE_MEMORY_PATH, ParentManagedMemory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Buddy's parent-approved memory.")
    parser.add_argument("--file", type=Path, default=DEFAULT_PROFILE_MEMORY_PATH)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    set_command = commands.add_parser("set")
    set_command.add_argument("key")
    set_command.add_argument("value")
    delete_command = commands.add_parser("delete")
    delete_command.add_argument("key")
    clear_command = commands.add_parser("clear")
    clear_command.add_argument("--yes", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    memory = ParentManagedMemory(args.file)
    if args.command == "list":
        facts = memory.load()
        if not facts:
            print("memory=empty")
        for key, value in sorted(facts.items()):
            print(f"{key}={value}")
        return 0
    if args.command == "set":
        memory.set(args.key, args.value)
        print(f"saved={args.key}")
        return 0
    if args.command == "delete":
        removed = memory.delete(args.key)
        print(f"deleted={args.key}" if removed else f"not-found={args.key}")
        return 0
    if not args.yes:
        raise RuntimeError("Add --yes to clear all parent-managed memory.")
    memory.clear()
    print("memory=cleared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
