#!/usr/bin/env bash
set -euo pipefail

buddy_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
expected_dir="/home/shofukus/buddy"
service_name="buddy-conversation.service"

if [[ "$buddy_dir" != "$expected_dir" ]]; then
  echo "Expected repository at $expected_dir, but found $buddy_dir" >&2
  echo "Edit infra/$service_name if the Raspberry Pi user or path changed." >&2
  exit 1
fi

for required_path in \
  "$buddy_dir/.env" \
  "$buddy_dir/.venv/bin/python" \
  "$buddy_dir/models/wakeword/vosk-model-small-ja-0.22" \
  "$buddy_dir/models/person_detection/person_detection_mediapipe_2023mar.onnx" \
  "$buddy_dir/models/person_detection/mp_persondet.py"; do
  if [[ ! -e "$required_path" ]]; then
    echo "Missing required path: $required_path" >&2
    exit 1
  fi
done

if ! grep -Eq '^OPENAI_API_KEY=.+$' "$buddy_dir/.env"; then
  echo "OPENAI_API_KEY is missing or empty in $buddy_dir/.env" >&2
  exit 1
fi

chmod 600 "$buddy_dir/.env"
sudo install -m 0644 \
  "$buddy_dir/infra/$service_name" \
  "/etc/systemd/system/$service_name"
sudo systemctl daemon-reload
sudo systemctl enable "$service_name"
sudo systemctl restart "$service_name"
sudo systemctl --no-pager --full status "$service_name"
