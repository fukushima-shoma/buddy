#!/usr/bin/env bash
set -u

services=(buddy-conversation.service buddy-ros-follow.service)

section() {
  printf '\n## %s\n' "$1"
}

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemd=not-available"
  exit 0
fi

for service in "${services[@]}"; do
  section "${service} status"
  systemctl --no-pager --full status "${service}" 2>&1 || true

  section "${service} recent errors"
  if command -v journalctl >/dev/null 2>&1; then
    journalctl --no-pager -u "${service}" -p warning -n 50 2>&1 || true
  else
    echo "journalctl=not-available"
  fi
done
