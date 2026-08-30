#!/usr/bin/env bash
set -euo pipefail

buddy_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
expected_dir="/home/shofukus/buddy"
conversation_service="buddy-conversation.service"
follow_service="buddy-ros-follow.service"

if [[ "$buddy_dir" != "$expected_dir" ]]; then
  echo "Expected repository at $expected_dir, but found $buddy_dir" >&2
  echo "Edit infra service files if the Raspberry Pi user or path changed." >&2
  exit 1
fi

for required_path in \
  "$buddy_dir/.env" \
  "$buddy_dir/.venv/bin/python" \
  "/home/shofukus/ros2_lyrical/install/local_setup.bash" \
  "/home/shofukus/buddy_ros2_ws/install/setup.bash" \
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
chmod +x \
  "$buddy_dir/scripts/run_buddy_conversation_ros2.sh" \
  "$buddy_dir/scripts/run_buddy_ros_follow.sh" \
  "$buddy_dir/scripts/stop_buddy_ros_follow.sh"
sudo install -m 0644 \
  "$buddy_dir/infra/$follow_service" \
  "/etc/systemd/system/$follow_service"
sudo install -m 0644 \
  "$buddy_dir/infra/$conversation_service" \
  "/etc/systemd/system/$conversation_service"
sudo systemctl daemon-reload
sudo systemctl enable "$follow_service" "$conversation_service"
sudo systemctl stop "$conversation_service"
sudo systemctl restart "$follow_service"
sudo systemctl restart "$conversation_service"
sudo systemctl --no-pager --full status "$follow_service"
sudo systemctl --no-pager --full status "$conversation_service"
