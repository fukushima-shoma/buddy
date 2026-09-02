#!/usr/bin/env bash
set -u

repo_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

section() {
  printf '\n## %s\n' "$1"
}

run_if_available() {
  local command_name="$1"
  shift
  if command -v "${command_name}" >/dev/null 2>&1; then
    "$@" 2>&1 || true
  else
    echo "${command_name}=not-available"
  fi
}

section "Host"
date -u '+timestamp_utc=%Y-%m-%dT%H:%M:%SZ'
uname -a 2>&1 || true
if [[ -r /etc/os-release ]]; then
  sed -n '1,20p' /etc/os-release
fi

section "CPU temperature"
if [[ -r /sys/class/thermal/thermal_zone0/temp ]]; then
  awk '{printf "cpu_temp_c=%.1f\n", $1 / 1000}' /sys/class/thermal/thermal_zone0/temp
elif command -v vcgencmd >/dev/null 2>&1; then
  vcgencmd measure_temp 2>&1 || true
else
  echo "cpu_temperature=not-available"
fi

section "Memory and disk"
run_if_available free free -h
df -h "${repo_dir}" 2>&1 || true

section "CPU and memory usage"
"${repo_dir}/scripts/monitor_buddy_resources.sh" --interval 1 --count 1 2>&1 || true

section "Raspberry Pi power"
if command -v vcgencmd >/dev/null 2>&1; then
  vcgencmd get_throttled 2>&1 || true
else
  echo "vcgencmd=not-available"
fi

section "Buddy services"
"${repo_dir}/scripts/check_buddy_services.sh" 2>&1 || true

section "ROS 2 graph"
"${repo_dir}/scripts/check_ros2_topics.sh" 2>&1 || true

section "I2C"
if command -v i2cdetect >/dev/null 2>&1; then
  i2cdetect -l 2>&1 || true
else
  echo "i2cdetect=not-available"
fi

section "Camera"
if command -v rpicam-hello >/dev/null 2>&1; then
  rpicam-hello --list-cameras 2>&1 || true
elif command -v libcamera-hello >/dev/null 2>&1; then
  libcamera-hello --list-cameras 2>&1 || true
elif command -v system_profiler >/dev/null 2>&1; then
  system_profiler SPCameraDataType 2>&1 || true
else
  echo "camera-enumerator=not-available"
fi

section "Audio"
run_if_available arecord arecord -l
run_if_available aplay aplay -l

section "Git"
git -C "${repo_dir}" status --short --branch 2>&1 || true
git -C "${repo_dir}" remote -v 2>&1 || true
