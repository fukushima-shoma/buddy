---
name: buddy-ros2-test
description: Run a consistent, safety-gated ROS 2 test workflow for Buddy, from environment and package checks through mock launch and topic validation. Use for ROS 2 integration testing; do not use it for live motor testing without explicit authorization.
---

# Buddy ROS 2 test

Prefer mock-backed tests and prove the ROS graph before considering real hardware.

## Workflow

1. Read `docs/phase4.md`, `docs/phase5.md`, the relevant launch file, and its tests.
2. Run the smallest Python tests for the affected nodes. Use the repository virtual environment when available.
3. Source `scripts/source_ros2.sh` in a Bash shell. If the underlay or overlay is missing, report the missing path; do not install or rebuild automatically.
4. Confirm `buddy_robot` is discoverable with `ros2 pkg prefix buddy_robot`.
5. Launch only mock backends. Never select `gpiozero`, `raspberry_pi`, `picamera2`, ALSA recording, or another real-device backend during the mock stage.
6. Run `scripts/check_ros2_topics.sh` and verify the relevant nodes and topics. Expected core interfaces include `/cmd_vel`, `/odom`, `/tf`, and `/tf_static`; absence may be valid when its owning node is not part of the chosen launch.
7. Stop the mock launch cleanly and report commands, observed nodes/topics, test results, and gaps.

Move to an actual-device test only when mock tests pass, the graph is correct, one process owns each GPIO device, emergency stop behavior is known, and the user explicitly authorizes the named hardware test. Keep wheels off the ground for the first motor-integrated run.
