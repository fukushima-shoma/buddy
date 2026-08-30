#!/usr/bin/env bash

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "Run this script with: source ~/buddy/scripts/source_ros2.sh" >&2
  exit 2
fi

buddy_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
buddy_repo_dir="$(dirname "${buddy_script_dir}")"
buddy_ros2_underlay="${BUDDY_ROS2_UNDERLAY:-${HOME}/ros2_lyrical/install/local_setup.bash}"
buddy_ros2_overlay="${BUDDY_ROS2_OVERLAY:-${HOME}/buddy_ros2_ws/install/setup.bash}"

if [[ ! -f "${buddy_ros2_underlay}" ]]; then
  echo "ROS 2 underlay not found: ${buddy_ros2_underlay}" >&2
  return 1
fi
if [[ ! -f "${buddy_ros2_overlay}" ]]; then
  echo "Buddy ROS 2 overlay not found: ${buddy_ros2_overlay}" >&2
  return 1
fi

source "${buddy_ros2_underlay}"
source "${buddy_ros2_overlay}"

buddy_venv_python="${buddy_repo_dir}/.venv/bin/python"
if [[ -x "${buddy_venv_python}" ]]; then
  buddy_venv_site="$(${buddy_venv_python} -c \
    'import site; print(site.getsitepackages()[0])')"
  export PYTHONPATH="${buddy_venv_site}${PYTHONPATH:+:${PYTHONPATH}}"
fi

unset buddy_script_dir buddy_repo_dir buddy_ros2_underlay buddy_ros2_overlay
unset buddy_venv_python buddy_venv_site
