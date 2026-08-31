#!/usr/bin/env bash
set -eo pipefail

buddy_repo_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
source "${buddy_repo_dir}/scripts/source_ros2.sh"

exec ros2 launch buddy_robot buddy_follow.launch.py \
  motor_backend:=gpiozero \
  distance_backend:=vl53l1x \
  person_backend:=mediapipe \
  power_backend:=raspberry_pi \
  max_speed:=1.0
