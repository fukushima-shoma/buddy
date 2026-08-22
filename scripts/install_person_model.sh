#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
destination="$repo_root/models/person_detection"
temporary_directory="$(mktemp -d)"
trap 'rm -r -- "$temporary_directory"' EXIT

commit="47534e27c9851bb1128ccc0102f1145e27f23f98"
model_name="person_detection_mediapipe_2023mar.onnx"
helper_name="mp_persondet.py"
model_url="https://github.com/opencv/opencv_zoo/raw/$commit/models/person_detection_mediapipe/$model_name"
helper_url="https://raw.githubusercontent.com/opencv/opencv_zoo/$commit/models/person_detection_mediapipe/$helper_name"

curl -L --fail --output "$temporary_directory/$model_name" "$model_url"
curl -L --fail --output "$temporary_directory/$helper_name" "$helper_url"

model_checksum="47fd5599d6fa17608f03e0eb0ae230baa6e597d7e8a2c8199fe00abea55a701f"
helper_checksum="e530a8ebc3c218376d5dd1c13aa8ed39a850fac4dbcd6928144746b33477b9c7"
printf '%s  %s\n' "$model_checksum" "$temporary_directory/$model_name" | sha256sum --check
printf '%s  %s\n' "$helper_checksum" "$temporary_directory/$helper_name" | sha256sum --check

mkdir -p "$destination"
install -m 0644 "$temporary_directory/$model_name" "$destination/$model_name"
install -m 0644 "$temporary_directory/$helper_name" "$destination/$helper_name"
printf 'installed=%s\n' "$destination/$model_name"
