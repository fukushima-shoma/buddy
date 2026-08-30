#!/usr/bin/env bash
set -euo pipefail

buddy_repo_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
source "${buddy_repo_dir}/scripts/source_ros2.sh"

exec "${buddy_repo_dir}/.venv/bin/python" \
  -m robot.conversation_loop_cli "$@"
