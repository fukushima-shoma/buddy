#!/usr/bin/env bash
set -o pipefail

buddy_repo_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
source "${buddy_repo_dir}/scripts/source_ros2.sh" || exit 0

timeout 5 ros2 service call \
  /follow/enable \
  std_srvs/srv/SetBool \
  "{data: false}" >/dev/null 2>&1 || true
