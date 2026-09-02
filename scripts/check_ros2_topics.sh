#!/usr/bin/env bash
set -u

repo_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

section() {
  printf '\n## %s\n' "$1"
}

ros2_run() {
  if command -v ros2 >/dev/null 2>&1; then
    ros2 "$@"
  else
    bash -c 'source "$1" >/dev/null 2>&1 || exit 127; shift; ros2 "$@"' \
      _ "${repo_dir}/scripts/source_ros2.sh" "$@"
  fi
}

if ! ros2_run --help >/dev/null 2>&1; then
  echo "ros2=not-available"
  exit 0
fi

section "ROS 2 nodes"
ros2_run node list 2>&1 || true

section "ROS 2 topics and types"
ros2_run topic list -t 2>&1 || true

section "Core topic details"
for topic in /cmd_vel /odom /tf /tf_static; do
  echo "topic=${topic}"
  ros2_run topic info "${topic}" 2>&1 || true
done
